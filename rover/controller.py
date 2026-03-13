"""Cyberwave SDK wrapper for the UGV Beast Rover.

Provides async motor control, camera frame capture, ultrasonic sensor
access, and battery monitoring through the Cyberwave Twin API.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

try:
    import cyberwave as cw
except ImportError:
    cw = None  # graceful fallback for environments without SDK

from config import (
    CYBERWAVE_API_TOKEN,
    ROVER_TWIN_ID,
    OBSTACLE_THRESHOLD_CM,
    SWEEP_STEP_CM,
    TURN_STEP_DEG,
)

logger = logging.getLogger("breacher.rover")


@dataclass
class RoverPosition:
    """Dead-reckoned position relative to entry point."""
    x: float = 0.0       # cm from entry, positive = right
    y: float = 0.0       # cm from entry, positive = forward into room
    heading: float = 0.0  # degrees, 0 = facing into room, clockwise positive

    def to_pct(self, room_width_cm: float = 600, room_depth_cm: float = 450) -> dict:
        """Convert to 0-100 percentage coordinates for the UI tactical map."""
        return {
            "x": max(0, min(100, 50 + (self.x / room_width_cm) * 100)),
            "y": max(0, min(100, 100 - (self.y / room_depth_cm) * 100)),
        }

    def to_dict(self) -> dict:
        return {"x": round(self.x, 1), "y": round(self.y, 1), "heading": round(self.heading, 1)}


class RoverController:
    """High-level async interface to the UGV Beast Rover via Cyberwave SDK."""

    def __init__(self) -> None:
        self._twin = None
        self._connected = False
        self._position = RoverPosition()
        self._entry_position = RoverPosition()
        self._battery_pct: int = 100
        self._path_history: list[list[float]] = []
        self._lock = asyncio.Lock()
        self._camera_cap: Optional[cv2.VideoCapture] = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    async def connect(self, twin_id: str = "") -> None:
        """Connect to the Beast Rover via Cyberwave Twin API."""
        tid = twin_id or ROVER_TWIN_ID
        if not tid:
            raise ValueError("ROVER_TWIN_ID not set")

        logger.info("Connecting to rover twin: %s", tid)

        if cw is None:
            logger.warning("Cyberwave SDK not installed – running in stub mode")
            self._connected = True
            return

        loop = asyncio.get_event_loop()
        self._twin = await loop.run_in_executor(
            None, lambda: cw.twin(tid, token=CYBERWAVE_API_TOKEN)
        )
        self._connected = True
        self._record_path_point()
        logger.info("Rover connected")

    async def disconnect(self) -> None:
        if self._camera_cap and self._camera_cap.isOpened():
            self._camera_cap.release()
        self._connected = False
        logger.info("Rover disconnected")

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def position(self) -> RoverPosition:
        return self._position

    @property
    def path_history(self) -> list[list[float]]:
        return self._path_history

    # ------------------------------------------------------------------
    # Motor Control
    # ------------------------------------------------------------------

    async def move_forward(self, distance_cm: float = SWEEP_STEP_CM) -> None:
        async with self._lock:
            logger.debug("Moving forward %s cm", distance_cm)
            if self._twin:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._twin.publish_state({
                        "command": "move",
                        "direction": "forward",
                        "distance": distance_cm,
                    }),
                )
            rad = math.radians(self._position.heading)
            self._position.x += distance_cm * math.sin(rad)
            self._position.y += distance_cm * math.cos(rad)
            self._record_path_point()
            await asyncio.sleep(distance_cm / 50)  # ~50 cm/s travel estimate

    async def move_backward(self, distance_cm: float = SWEEP_STEP_CM) -> None:
        async with self._lock:
            logger.debug("Moving backward %s cm", distance_cm)
            if self._twin:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._twin.publish_state({
                        "command": "move",
                        "direction": "backward",
                        "distance": distance_cm,
                    }),
                )
            rad = math.radians(self._position.heading)
            self._position.x -= distance_cm * math.sin(rad)
            self._position.y -= distance_cm * math.cos(rad)
            self._record_path_point()
            await asyncio.sleep(distance_cm / 50)

    async def turn(self, degrees: float = TURN_STEP_DEG) -> None:
        """Rotate in place. Positive = clockwise."""
        async with self._lock:
            logger.debug("Turning %s degrees", degrees)
            if self._twin:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._twin.publish_state({
                        "command": "rotate",
                        "angle": degrees,
                    }),
                )
            self._position.heading = (self._position.heading + degrees) % 360
            await asyncio.sleep(abs(degrees) / 180)  # ~180 deg/s rotation

    async def stop(self) -> None:
        async with self._lock:
            logger.info("Rover STOP")
            if self._twin:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._twin.publish_state({"command": "stop"}),
                )

    # ------------------------------------------------------------------
    # Camera
    # ------------------------------------------------------------------

    async def get_camera_frame(self) -> Optional[np.ndarray]:
        """Capture a single frame from the rover's onboard camera."""
        if self._twin:
            try:
                loop = asyncio.get_event_loop()
                frame = await loop.run_in_executor(None, self._capture_sdk_frame)
                if frame is not None:
                    return frame
            except Exception as e:
                logger.warning("SDK camera capture failed, trying fallback: %s", e)

        if self._camera_cap is None:
            self._camera_cap = cv2.VideoCapture(0)
        if self._camera_cap.isOpened():
            ret, frame = self._camera_cap.read()
            if ret:
                return frame
        logger.warning("No camera frame available")
        return None

    def _capture_sdk_frame(self) -> Optional[np.ndarray]:
        """Blocking call to get a frame through the Cyberwave SDK."""
        if not self._twin:
            return None
        try:
            raw = self._twin.get_frame()
            if raw is not None:
                arr = np.frombuffer(raw, dtype=np.uint8)
                return cv2.imdecode(arr, cv2.IMREAD_COLOR)
        except AttributeError:
            pass
        return None

    # ------------------------------------------------------------------
    # Sensors
    # ------------------------------------------------------------------

    async def get_ultrasonic_distance(self) -> float:
        """Return front obstacle distance in cm. Returns 999 if no reading."""
        if self._twin:
            try:
                loop = asyncio.get_event_loop()
                state = await loop.run_in_executor(None, lambda: self._twin.get_state())
                if state and "ultrasonic" in state:
                    return float(state["ultrasonic"])
            except Exception as e:
                logger.warning("Ultrasonic read failed: %s", e)
        return 999.0

    async def get_battery(self) -> int:
        """Return battery percentage."""
        if self._twin:
            try:
                loop = asyncio.get_event_loop()
                state = await loop.run_in_executor(None, lambda: self._twin.get_state())
                if state and "battery" in state:
                    self._battery_pct = int(state["battery"])
            except Exception as e:
                logger.warning("Battery read failed: %s", e)
        return self._battery_pct

    async def get_position_description(self) -> str:
        """Human-readable position relative to entry point."""
        p = self._position
        dist = math.sqrt(p.x ** 2 + p.y ** 2)
        if dist < 10:
            return "At the entry point"
        direction = self._heading_to_compass(p.heading)
        return f"Approximately {dist:.0f} centimeters from entry, facing {direction}"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _record_path_point(self) -> None:
        pct = self._position.to_pct()
        self._path_history.append([round(pct["x"], 1), round(pct["y"], 1)])

    @staticmethod
    def _heading_to_compass(heading: float) -> str:
        dirs = ["north", "northeast", "east", "southeast",
                "south", "southwest", "west", "northwest"]
        idx = int(((heading + 22.5) % 360) / 45)
        return dirs[idx]

    def reset_position(self) -> None:
        self._position = RoverPosition()
        self._entry_position = RoverPosition()
        self._path_history = []
        self._record_path_point()

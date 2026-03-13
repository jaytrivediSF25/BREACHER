"""Cyberwave SDK wrapper for the UGV Beast Rover.

Verified Cyberwave Python SDK API (from pypi.org/project/cyberwave v0.3.20):
  - Cyberwave(token=..., source_type="tele") — remote teleop mode, sends
    commands through MQTT bridge to the physical rover
  - robot = cw.twin(twin_id="UUID") — get the rover's digital twin
  - robot.edit_position(x, y, z) — set twin position (propagated to device
    in tele mode via MQTT → ROS2 → ESP32)
  - robot.edit_rotation(yaw=deg) — set twin rotation
  - robot.joints.set("name", value, degrees=True) — actuate joints
  - robot.joints.get_all() — read joint states
  - robot.alerts.create(...) — push alerts to the dashboard

Camera: The SDK streams video FROM edge TO cloud (start_streaming).
There is no documented way to RECEIVE frames via the SDK from the cloud
side. We use a local OpenCV camera (webcam / USB) for vision analysis.

UGV Beast architecture:
  Cloud SDK (tele) → MQTT → Edge MQTT Bridge → ROS2 topics → UGV Driver
  → Serial UART → ESP32 (motors, encoders, IMU, camera servo)
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
    from cyberwave import Cyberwave
except ImportError:
    Cyberwave = None

from config import (
    CYBERWAVE_API_TOKEN,
    ROVER_TWIN_ID,
    SWEEP_STEP_CM,
    TURN_STEP_DEG,
    FRAME_RATE,
)

logger = logging.getLogger("breacher.rover")

CM_TO_METERS = 0.01


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
    """High-level async interface to the UGV Beast Rover via Cyberwave SDK.

    Motor commands use source_type="tele" so they propagate through the
    MQTT bridge to the physical hardware, not just update the 3D model.
    """

    def __init__(self) -> None:
        self._cw: Optional[object] = None
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
            raise ValueError("ROVER_TWIN_ID not set — check your .env")
        if not CYBERWAVE_API_TOKEN:
            raise ValueError("CYBERWAVE_API_TOKEN not set — check your .env")

        logger.info("Connecting to rover twin: %s", tid)

        if Cyberwave is None:
            logger.warning("Cyberwave SDK not installed — running in stub mode")
            self._connected = True
            return

        loop = asyncio.get_event_loop()

        def _connect():
            client = Cyberwave(token=CYBERWAVE_API_TOKEN, source_type="tele")
            twin = client.twin(twin_id=tid)
            return client, twin

        self._cw, self._twin = await loop.run_in_executor(None, _connect)

        self._connected = True
        self._record_path_point()
        logger.info("Rover connected (source_type=tele)")

    async def disconnect(self) -> None:
        if self._cw:
            try:
                self._cw.disconnect()
            except Exception:
                pass
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
    #
    # edit_position / edit_rotation are the documented SDK methods.
    # With source_type="tele", these propagate through MQTT → ROS2 →
    # ESP32 to move the physical rover.
    # ------------------------------------------------------------------

    async def move_forward(self, distance_cm: float = SWEEP_STEP_CM) -> None:
        async with self._lock:
            logger.debug("Moving forward %s cm", distance_cm)
            if self._twin:
                rad = math.radians(self._position.heading)
                dx = distance_cm * math.sin(rad) * CM_TO_METERS
                dz = distance_cm * math.cos(rad) * CM_TO_METERS
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._twin.edit_position(x=dx, y=0, z=dz),
                )
            rad = math.radians(self._position.heading)
            self._position.x += distance_cm * math.sin(rad)
            self._position.y += distance_cm * math.cos(rad)
            self._record_path_point()
            await asyncio.sleep(distance_cm / 50)

    async def move_backward(self, distance_cm: float = SWEEP_STEP_CM) -> None:
        async with self._lock:
            logger.debug("Moving backward %s cm", distance_cm)
            if self._twin:
                rad = math.radians(self._position.heading)
                dx = -(distance_cm * math.sin(rad) * CM_TO_METERS)
                dz = -(distance_cm * math.cos(rad) * CM_TO_METERS)
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._twin.edit_position(x=dx, y=0, z=dz),
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
                    lambda: self._twin.edit_rotation(yaw=degrees),
                )
            self._position.heading = (self._position.heading + degrees) % 360
            await asyncio.sleep(abs(degrees) / 180)

    async def stop(self) -> None:
        """Stop the rover. No SDK call — rover halts when no new
        movement commands arrive. Sending edit_position(0,0,0) would
        teleport to origin, which is wrong."""
        async with self._lock:
            logger.info("Rover STOP")

    # ------------------------------------------------------------------
    # Camera — local OpenCV only
    #
    # The Cyberwave SDK streams video FROM edge TO cloud (outbound).
    # There is no documented API to receive frames on the cloud/SDK side.
    # We capture locally from the laptop webcam or a USB camera connected
    # to the machine running BREACHER.
    # ------------------------------------------------------------------

    async def get_camera_frame(self) -> Optional[np.ndarray]:
        """Capture a single frame from a local camera."""
        if self._camera_cap is None:
            self._camera_cap = cv2.VideoCapture(0)
        if self._camera_cap.isOpened():
            ret, frame = self._camera_cap.read()
            if ret:
                return frame
        logger.warning("No camera frame available")
        return None

    # ------------------------------------------------------------------
    # Sensors — UGV Beast has IMU + encoders, no ultrasonic
    # ------------------------------------------------------------------

    async def get_battery(self) -> int:
        """Return battery percentage (estimated if SDK unavailable)."""
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

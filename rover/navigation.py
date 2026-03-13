"""Autonomous room sweep using clockwise wall-following.

Implements the PRD's F-LOC-01 through F-LOC-05: autonomous navigation,
obstacle avoidance, doorway detection, multi-room sequential clearance,
and voice-commanded directional overrides.
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Callable, Optional

from config import (
    OBSTACLE_THRESHOLD_CM,
    SWEEP_STEP_CM,
    TURN_STEP_DEG,
    AlertTier,
)
from rover.controller import RoverController

logger = logging.getLogger("breacher.nav")


class SweepState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_DOORWAY = "waiting_doorway"
    RETURNING = "returning"
    COMPLETE = "complete"
    ABORTED = "aborted"


class AutonomousSweep:
    """Clockwise wall-following room sweep with obstacle avoidance."""

    def __init__(self, controller: RoverController) -> None:
        self._ctrl = controller
        self._state = SweepState.IDLE
        self._sweep_pct: float = 0.0
        self._quadrants = {"NW": "pending", "NE": "pending", "SW": "pending", "SE": "pending"}
        self._iterations: int = 0
        self._max_iterations: int = 40
        self._cancel_event = asyncio.Event()
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # not paused initially
        self._doorway_continue_event = asyncio.Event()

        # Callbacks set by the orchestrator
        self.on_frame_needed: Optional[Callable] = None       # request a vision frame
        self.on_doorway_detected: Optional[Callable] = None
        self.on_sweep_progress: Optional[Callable] = None
        self.on_sweep_complete: Optional[Callable] = None

    @property
    def state(self) -> SweepState:
        return self._state

    @property
    def sweep_pct(self) -> float:
        return self._sweep_pct

    @property
    def quadrants(self) -> dict:
        return dict(self._quadrants)

    # ------------------------------------------------------------------
    # Main sweep loop
    # ------------------------------------------------------------------

    async def start_sweep(self) -> None:
        """Execute the full clockwise wall-following sweep."""
        if self._state == SweepState.RUNNING:
            return
        self._state = SweepState.RUNNING
        self._cancel_event.clear()
        self._iterations = 0
        self._sweep_pct = 0
        self._update_quadrant_progress()
        logger.info("Autonomous sweep started")

        try:
            while self._iterations < self._max_iterations:
                if self._cancel_event.is_set():
                    break
                await self._pause_event.wait()

                dist = await self._ctrl.get_ultrasonic_distance()

                if dist < OBSTACLE_THRESHOLD_CM:
                    if self._is_possible_doorway(dist):
                        await self._handle_doorway()
                        if self._cancel_event.is_set():
                            break
                    else:
                        await self._ctrl.turn(TURN_STEP_DEG)
                else:
                    await self._ctrl.move_forward(SWEEP_STEP_CM)

                self._iterations += 1
                self._sweep_pct = min(100, (self._iterations / self._max_iterations) * 100)
                self._update_quadrant_progress()

                if self.on_frame_needed:
                    await self.on_frame_needed()

                if self.on_sweep_progress and self._iterations % 5 == 0:
                    await self.on_sweep_progress(self._sweep_pct)

            if not self._cancel_event.is_set():
                self._state = SweepState.COMPLETE
                self._sweep_pct = 100
                self._quadrants = {k: "done" for k in self._quadrants}
                if self.on_sweep_complete:
                    await self.on_sweep_complete()
                logger.info("Sweep complete")
            else:
                self._state = SweepState.ABORTED
                logger.info("Sweep aborted")

        except Exception as e:
            logger.error("Sweep error: %s", e, exc_info=True)
            self._state = SweepState.ABORTED

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------

    async def pause(self) -> None:
        self._pause_event.clear()
        self._state = SweepState.PAUSED
        await self._ctrl.stop()
        logger.info("Sweep paused")

    async def resume(self) -> None:
        self._pause_event.set()
        self._state = SweepState.RUNNING
        logger.info("Sweep resumed")

    async def abort(self) -> None:
        """Immediate stop — highest priority."""
        self._cancel_event.set()
        self._pause_event.set()  # unblock if paused
        self._doorway_continue_event.set()  # unblock if waiting
        await self._ctrl.stop()
        self._state = SweepState.ABORTED
        logger.info("Sweep ABORT")

    async def continue_through_doorway(self) -> None:
        self._doorway_continue_event.set()

    async def redirect(self, direction: str) -> None:
        """Voice-commanded directional override (e.g. 'check behind the couch')."""
        logger.info("Redirect: %s", direction)
        was_running = self._state == SweepState.RUNNING
        if was_running:
            await self.pause()

        direction_lower = direction.lower()
        if "left" in direction_lower:
            await self._ctrl.turn(-90)
        elif "right" in direction_lower:
            await self._ctrl.turn(90)
        elif "back" in direction_lower or "behind" in direction_lower:
            await self._ctrl.turn(180)

        await self._ctrl.move_forward(SWEEP_STEP_CM * 2)

        if was_running:
            await self.resume()

    async def return_to_entry(self) -> None:
        """Navigate back toward the entry point using dead reckoning."""
        self._state = SweepState.RETURNING
        logger.info("Returning to entry")
        pos = self._ctrl.position
        import math
        angle_to_entry = math.degrees(math.atan2(-pos.x, -pos.y))
        turn_needed = (angle_to_entry - pos.heading + 360) % 360
        if turn_needed > 180:
            turn_needed -= 360
        await self._ctrl.turn(turn_needed)
        dist = math.sqrt(pos.x ** 2 + pos.y ** 2)
        await self._ctrl.move_forward(dist)
        self._state = SweepState.COMPLETE

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _is_possible_doorway(self, distance: float) -> bool:
        """Heuristic: a very short ultrasonic reading that suddenly opens up
        could indicate a doorway rather than a wall."""
        return distance > OBSTACLE_THRESHOLD_CM * 0.3

    async def _handle_doorway(self) -> None:
        self._state = SweepState.WAITING_DOORWAY
        logger.info("Possible doorway detected")
        if self.on_doorway_detected:
            await self.on_doorway_detected()

        self._doorway_continue_event.clear()
        try:
            await asyncio.wait_for(self._doorway_continue_event.wait(), timeout=30.0)
            await self._ctrl.move_forward(SWEEP_STEP_CM * 2)
            self._state = SweepState.RUNNING
        except asyncio.TimeoutError:
            logger.info("Doorway continue timed out, resuming sweep")
            await self._ctrl.turn(TURN_STEP_DEG)
            self._state = SweepState.RUNNING

    def _update_quadrant_progress(self) -> None:
        pct = self._sweep_pct
        quadrant_order = ["NW", "NE", "SW", "SE"]
        for i, q in enumerate(quadrant_order):
            threshold = (i + 1) * 25
            if pct >= threshold:
                self._quadrants[q] = "done"
            elif pct >= threshold - 25:
                self._quadrants[q] = "active"
            else:
                self._quadrants[q] = "pending"

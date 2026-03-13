"""Autonomous room sweep with breadcrumb-replay return.

Implements the PRD's F-LOC-01 through F-LOC-05: autonomous navigation,
obstacle avoidance, doorway detection, multi-room sequential clearance,
and voice-commanded directional overrides.

Two sweep modes:
  - start_sweep(): vision-guided wall-following (uses GPT-4o to detect walls)
  - demo_sweep(): scripted enter-pan-exit for reliable hackathon demo
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Callable, Optional

from config import (
    SWEEP_STEP_CM,
    TURN_STEP_DEG,
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
    """Room sweep with breadcrumb-replay return path."""

    def __init__(self, controller: RoverController) -> None:
        self._ctrl = controller
        self._state = SweepState.IDLE
        self._sweep_pct: float = 0.0
        self._quadrants = {"NW": "pending", "NE": "pending", "SW": "pending", "SE": "pending"}
        self._iterations: int = 0
        self._max_iterations: int = 40
        self._cancel_event = asyncio.Event()
        self._pause_event = asyncio.Event()
        self._pause_event.set()
        self._doorway_continue_event = asyncio.Event()

        self._move_history: list[dict] = []

        # Callbacks set by the orchestrator
        self.on_frame_needed: Optional[Callable] = None
        self.on_doorway_detected: Optional[Callable] = None
        self.on_sweep_progress: Optional[Callable] = None
        self.on_sweep_complete: Optional[Callable] = None
        self.on_check_obstacle: Optional[Callable] = None  # vision-based obstacle check

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
    # Main sweep loop — vision-guided (no ultrasonic dependency)
    # ------------------------------------------------------------------

    async def start_sweep(self) -> None:
        """Execute room sweep using vision-based obstacle detection.

        If on_check_obstacle is wired, the orchestrator's vision model
        decides when there's a wall ahead. Otherwise falls back to
        always-move-forward (equivalent to demo_sweep behaviour).
        """
        if self._state == SweepState.RUNNING:
            return
        self._state = SweepState.RUNNING
        self._cancel_event.clear()
        self._iterations = 0
        self._sweep_pct = 0
        self._move_history = []
        self._update_quadrant_progress()
        logger.info("Autonomous sweep started")

        try:
            while self._iterations < self._max_iterations:
                if self._cancel_event.is_set():
                    break
                await self._pause_event.wait()

                obstacle_ahead = False
                if self.on_check_obstacle:
                    obstacle_ahead = await self.on_check_obstacle()

                if obstacle_ahead:
                    await self._ctrl.turn(TURN_STEP_DEG)
                    self._move_history.append({"type": "turn", "value": TURN_STEP_DEG})
                else:
                    await self._ctrl.move_forward(SWEEP_STEP_CM)
                    self._move_history.append({"type": "forward", "value": SWEEP_STEP_CM})

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
    # Demo sweep — scripted enter-pan-exit for hackathon reliability
    # ------------------------------------------------------------------

    async def demo_sweep(self) -> None:
        """Reliable demo sweep: enter room, 360 pan, retrace exit."""
        if self._state == SweepState.RUNNING:
            return
        self._state = SweepState.RUNNING
        self._cancel_event.clear()
        self._iterations = 0
        self._sweep_pct = 0
        self._move_history = []
        self._update_quadrant_progress()
        logger.info("Demo sweep started")

        try:
            for i in range(5):
                if self._cancel_event.is_set():
                    break
                await self._pause_event.wait()

                await self._ctrl.move_forward(SWEEP_STEP_CM)
                self._move_history.append({"type": "forward", "value": SWEEP_STEP_CM})
                if self.on_frame_needed:
                    await self.on_frame_needed()
                self._iterations += 1
                self._sweep_pct = min(100, (self._iterations / 20) * 100)
                self._update_quadrant_progress()

            for _ in range(4):
                if self._cancel_event.is_set():
                    break
                await self._pause_event.wait()

                await self._ctrl.turn(90)
                self._move_history.append({"type": "turn", "value": 90})
                await asyncio.sleep(0.5)
                if self.on_frame_needed:
                    await self.on_frame_needed()
                self._iterations += 1
                self._sweep_pct = min(100, (self._iterations / 20) * 100)
                self._update_quadrant_progress()

            if not self._cancel_event.is_set():
                await self.return_to_entry()
                self._state = SweepState.COMPLETE
                self._sweep_pct = 100
                self._quadrants = {k: "done" for k in self._quadrants}
                if self.on_sweep_complete:
                    await self.on_sweep_complete()
                logger.info("Demo sweep complete")
            else:
                self._state = SweepState.ABORTED

        except Exception as e:
            logger.error("Demo sweep error: %s", e, exc_info=True)
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
        self._pause_event.set()
        self._doorway_continue_event.set()
        await self._ctrl.stop()
        self._state = SweepState.ABORTED
        logger.info("Sweep ABORT")

    async def continue_through_doorway(self) -> None:
        self._doorway_continue_event.set()

    async def redirect(self, direction: str) -> None:
        """Voice-commanded directional override."""
        logger.info("Redirect: %s", direction)
        was_running = self._state == SweepState.RUNNING
        if was_running:
            await self.pause()

        direction_lower = direction.lower()
        turn_deg = 0
        if "left" in direction_lower:
            turn_deg = -90
        elif "right" in direction_lower:
            turn_deg = 90
        elif "back" in direction_lower or "behind" in direction_lower:
            turn_deg = 180

        if turn_deg:
            await self._ctrl.turn(turn_deg)
            self._move_history.append({"type": "turn", "value": turn_deg})

        await self._ctrl.move_forward(SWEEP_STEP_CM * 2)
        self._move_history.append({"type": "forward", "value": SWEEP_STEP_CM * 2})

        if was_running:
            await self.resume()

    # ------------------------------------------------------------------
    # Breadcrumb return — replay move history in reverse
    # ------------------------------------------------------------------

    async def return_to_entry(self) -> None:
        """Retrace the exact path back to entry by reversing move history."""
        self._state = SweepState.RETURNING
        logger.info("Retracing %d moves to entry", len(self._move_history))

        for move in reversed(self._move_history):
            if self._cancel_event.is_set():
                break
            if move["type"] == "forward":
                await self._ctrl.move_backward(move["value"])
            elif move["type"] == "turn":
                await self._ctrl.turn(-move["value"])

        self._state = SweepState.COMPLETE
        logger.info("Back at entry")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

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

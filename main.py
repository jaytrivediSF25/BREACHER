"""BREACHER — Main Orchestrator

Wires together the four async threads (vision, TTS, STT, navigation),
the WebSocket server for the Mission Debrief UI, and manages the full
mission lifecycle.
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
import sys
import time

import websockets

from config import (
    FRAME_RATE,
    WS_HOST,
    WS_PORT,
    MISSION_PROFILE,
    TERMINOLOGY_MODE,
    MissionState,
    MissionProfile,
    AlertTier,
    PROFILE_CONFIG,
)
from rover.controller import RoverController
from rover.navigation import AutonomousSweep, SweepState
from vision.analyzer import VisionAnalyzer
from vision.scene_model import SceneModel, ChangeType
from voice.tts import TTSEngine
from voice.stt import STTEngine
from voice.alert_manager import AlertManager
from voice.briefing import BriefingGenerator
from command.parser import CommandParser, BreacherContext

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("breacher.main")

# ---------------------------------------------------------------------------
# WebSocket broadcast (UI bridge at ws://localhost:8765)
# ---------------------------------------------------------------------------
connected_clients: set = set()


async def broadcast(scene: SceneModel, sweep, rover, tts, voice_line=None):
    """Push scene state (and optional voice line) to all connected UI clients."""
    if not connected_clients:
        return

    scene_dict = scene.to_dict()
    scene_dict["sweepPct"] = round(sweep.sweep_pct, 1)
    scene_dict["quadrants"] = sweep.quadrants
    scene_dict["roverPosition"] = rover.position.to_pct()
    scene_dict["roverPath"] = rover.path_history[-200:]
    scene_dict["latencyMs"] = round(tts.last_latency_ms, 0)
    scene_dict["fpsCurrent"] = FRAME_RATE
    scene_dict["batteryPct"] = await rover.get_battery()
    scene_dict["ttsActive"] = tts.is_speaking

    msg = {"sceneState": scene_dict}
    if voice_line:
        msg["voiceLine"] = voice_line

    payload = json.dumps(msg)
    await asyncio.gather(
        *[client.send(payload) for client in connected_clients],
        return_exceptions=True,
    )


async def ws_handler(websocket):
    """Handle an incoming WebSocket connection from the UI."""
    connected_clients.add(websocket)
    logger.info("UI client connected (%d total)", len(connected_clients))
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                cmd = data.get("command", "")
                if cmd:
                    logger.info("UI command received: %s", cmd)
            except json.JSONDecodeError:
                pass
        await websocket.wait_closed()
    finally:
        connected_clients.discard(websocket)
        logger.info("UI client disconnected (%d remaining)", len(connected_clients))


# ---------------------------------------------------------------------------
# Main BREACHER system
# ---------------------------------------------------------------------------

class BreacherSystem:
    """Top-level orchestrator managing the full mission lifecycle."""

    def __init__(self) -> None:
        self.state = MissionState.STANDBY
        self.profile = MISSION_PROFILE
        self.profile_config = PROFILE_CONFIG[self.profile]

        # Subsystems
        self.rover = RoverController()
        self.nav = AutonomousSweep(self.rover)
        self.vision = VisionAnalyzer()
        self.scene = SceneModel()
        self.tts = TTSEngine()
        self.stt = STTEngine()
        self.alert_mgr = AlertManager()
        self.briefing = BriefingGenerator(TERMINOLOGY_MODE)
        self.cmd_parser = CommandParser()

        # Wiring
        self.alert_mgr.set_tts(self.tts)
        self.stt.on_command = self._handle_voice_command
        self.stt.on_speech_detected = self._handle_barge_in
        self.nav.on_frame_needed = self._vision_frame
        self.nav.on_doorway_detected = self._on_doorway
        self.nav.on_sweep_progress = self._on_sweep_progress
        self.nav.on_sweep_complete = self._on_sweep_complete

        self._ctx = BreacherContext(
            rover=self.rover,
            nav=self.nav,
            scene_model=self.scene,
            alert_mgr=self.alert_mgr,
            briefing=self.briefing,
            tts=self.tts,
            mission_profile=self.profile,
            on_deploy=self._start_mission,
        )

        self._vision_task: asyncio.Task | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        logger.info("Initializing BREACHER system...")
        await self.rover.connect()
        await self.tts.initialize()
        self.state = MissionState.STANDBY
        logger.info("System ready — state: STANDBY")

    async def run(self) -> None:
        """Main run loop — starts all concurrent tasks."""
        self._running = True

        ws_server = await websockets.serve(ws_handler, WS_HOST, WS_PORT)
        logger.info("WebSocket server started on ws://%s:%d", WS_HOST, WS_PORT)

        tasks = [
            asyncio.create_task(self.alert_mgr.consume_loop(), name="tts_loop"),
            asyncio.create_task(self._stt_loop(), name="stt_loop"),
        ]

        await self.alert_mgr.enqueue("Breacher online. Standing by.", AlertTier.P4_STATUS)
        await self._broadcast()

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("System shutting down...")
        finally:
            ws_server.close()
            await ws_server.wait_closed()
            await self.shutdown()

    async def shutdown(self) -> None:
        self._running = False
        self.alert_mgr.stop()
        await self.stt.stop_listening()
        await self.nav.abort()
        await self.tts.shutdown()
        await self.rover.disconnect()
        logger.info("BREACHER shut down")

    # ------------------------------------------------------------------
    # Mission flow
    # ------------------------------------------------------------------

    async def _start_mission(self) -> None:
        """Called when 'Breacher, go' is received."""
        if self.state in (MissionState.SWEEPING, MissionState.DEPLOYED):
            return

        self.state = MissionState.DEPLOYED
        self.scene.reset()
        self.rover.reset_position()
        logger.info("Mission started — DEPLOYED")

        self._vision_task = asyncio.create_task(self._sweep_and_scan(), name="sweep_scan")

    async def _sweep_and_scan(self) -> None:
        """Run the navigation sweep with interleaved vision analysis."""
        self.state = MissionState.SWEEPING
        await self.nav.start_sweep()

        if self.nav.state == SweepState.COMPLETE:
            self.state = MissionState.COMPLETE
            sitrep = self.briefing.initial_sitrep(self.scene)
            self.scene.log_tts(sitrep)
            await self.alert_mgr.enqueue(sitrep, AlertTier.P2_WARNING)
            await self._broadcast(voice_line={
                "speaker": "BREACHER",
                "text": sitrep,
                "ts": self.scene.get_elapsed(),
            })

            if self.profile_config.get("loop"):
                await asyncio.sleep(5)
                await self._start_mission()

    # ------------------------------------------------------------------
    # Thread 1: Vision loop (called per frame during sweep)
    # ------------------------------------------------------------------

    async def _vision_frame(self) -> None:
        """Capture and analyze a single frame during the sweep."""
        frame = await self.rover.get_camera_frame()
        if frame is None:
            return

        analysis = await self.vision.analyze_frame(frame)
        changes = self.scene.update(analysis)

        for change in changes:
            if change.change_type == ChangeType.NO_CHANGE:
                continue

            if not self.profile_config.get("narrate_layout") and change.change_type == ChangeType.LAYOUT_UPDATE:
                continue

            alert_text = self.briefing.change_alert(change)
            if alert_text and self.profile_config.get("tts_enabled"):
                self.scene.log_tts(alert_text)
                await self.alert_mgr.enqueue(alert_text, change.priority)
                await self._broadcast(voice_line={
                    "speaker": "BREACHER",
                    "text": alert_text,
                    "ts": self.scene.get_elapsed(),
                })

        await self._broadcast()

        await asyncio.sleep(1.0 / FRAME_RATE)

    # ------------------------------------------------------------------
    # Thread 3: STT loop
    # ------------------------------------------------------------------

    async def _stt_loop(self) -> None:
        await self.stt.start_listening()
        while self._running:
            await asyncio.sleep(0.5)

    def _handle_voice_command(self, command_text: str) -> None:
        """Callback from STT engine when a command is detected."""
        logger.info("Voice command: %s", command_text)
        cmd = self.cmd_parser.parse(command_text)

        asyncio.create_task(self._broadcast(voice_line={
            "speaker": "OPERATOR",
            "text": f"Breacher, {command_text}",
            "ts": self.scene.get_elapsed(),
        }))

        asyncio.create_task(self.cmd_parser.execute(cmd, self._ctx))

    def _handle_barge_in(self) -> None:
        """Called when any speech is detected — cancel current TTS for barge-in."""
        if self.tts.is_speaking:
            asyncio.create_task(self.tts.cancel())

    # ------------------------------------------------------------------
    # Navigation callbacks
    # ------------------------------------------------------------------

    async def _on_doorway(self) -> None:
        msg = self.briefing.doorway_detected()
        self.scene.log_tts(msg)
        await self.alert_mgr.enqueue(msg, AlertTier.P3_UPDATE)
        await self._broadcast(voice_line={
            "speaker": "BREACHER", "text": msg, "ts": self.scene.get_elapsed(),
        })

    async def _on_sweep_progress(self, pct: float) -> None:
        msg = self.briefing.sweep_progress(pct)
        if self.profile_config.get("tts_enabled"):
            await self.alert_mgr.enqueue(msg, AlertTier.P4_STATUS)
        await self._broadcast()

    async def _on_sweep_complete(self) -> None:
        logger.info("Sweep complete callback")
        await self._broadcast()

    # ------------------------------------------------------------------
    # Broadcast helper
    # ------------------------------------------------------------------

    async def _broadcast(self, voice_line=None) -> None:
        await broadcast(self.scene, self.nav, self.rover, self.tts, voice_line)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    system = BreacherSystem()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(system.shutdown()))

    try:
        loop.run_until_complete(system.initialize())
        loop.run_until_complete(system.run())
    except KeyboardInterrupt:
        logger.info("Interrupted")
    finally:
        loop.run_until_complete(system.shutdown())
        loop.close()


if __name__ == "__main__":
    main()

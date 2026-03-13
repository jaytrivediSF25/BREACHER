"""Smallest.ai Pulse STT engine via WebSocket.

Streams microphone audio to the Pulse real-time STT API, detects the
"Breacher" wake word, supports barge-in, and fires a callback with the
parsed command text.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable, Optional
from urllib.parse import urlencode

import numpy as np
import sounddevice as sd

try:
    import websockets
    HAS_WS = True
except ImportError:
    HAS_WS = False

from config import (
    SMALLEST_API_KEY,
    STT_CHUNK_SIZE,
    STT_CHUNK_INTERVAL_MS,
    STT_SAMPLE_RATE,
    STT_LANGUAGE,
)

logger = logging.getLogger("breacher.stt")

PULSE_BASE_URL = "wss://api.smallest.ai/waves/v1/pulse/get_text"
WAKE_WORD = "breacher"


class STTEngine:
    """Streaming speech-to-text via Smallest.ai Pulse with wake word detection."""

    def __init__(self) -> None:
        self.on_command: Optional[Callable[[str], None]] = None
        self.on_speech_detected: Optional[Callable[[], None]] = None

        self._ws = None
        self._running = False
        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._mic_stream: Optional[sd.InputStream] = None
        self._tasks: list[asyncio.Task] = []

    async def start_listening(self) -> None:
        """Start the mic capture and STT WebSocket loops."""
        if self._running:
            return
        self._running = True

        self._tasks = [
            asyncio.create_task(self._mic_capture_loop()),
            asyncio.create_task(self._ws_loop()),
        ]
        logger.info("STT listening started")

    async def stop_listening(self) -> None:
        self._running = False
        if self._mic_stream:
            self._mic_stream.stop()
            self._mic_stream.close()
            self._mic_stream = None
        if self._ws:
            try:
                await self._ws.send(json.dumps({"type": "finalize"}))
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()
        logger.info("STT listening stopped")

    # ------------------------------------------------------------------
    # Microphone capture
    # ------------------------------------------------------------------

    async def _mic_capture_loop(self) -> None:
        """Capture audio from the default microphone and feed the queue."""
        loop = asyncio.get_event_loop()

        def audio_callback(indata, frames, time_info, status):
            if status:
                logger.debug("Mic status: %s", status)
            pcm = (indata[:, 0] * 32768).astype(np.int16).tobytes()
            try:
                self._audio_queue.put_nowait(pcm)
            except asyncio.QueueFull:
                pass

        try:
            self._mic_stream = sd.InputStream(
                samplerate=STT_SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=STT_CHUNK_SIZE // 2,  # 16-bit = 2 bytes per sample
                callback=audio_callback,
            )
            self._mic_stream.start()
            logger.info("Mic capture started at %d Hz", STT_SAMPLE_RATE)

            while self._running:
                await asyncio.sleep(0.1)

        except Exception as e:
            logger.error("Mic capture error: %s", e, exc_info=True)

    # ------------------------------------------------------------------
    # WebSocket STT loop
    # ------------------------------------------------------------------

    async def _ws_loop(self) -> None:
        """Maintain WebSocket connection to Pulse STT and process transcripts."""
        if not HAS_WS:
            logger.error("websockets library not installed — STT disabled")
            return
        if not SMALLEST_API_KEY:
            logger.error("SMALLEST_API_KEY not set — STT disabled")
            return

        while self._running:
            try:
                await self._ws_session()
            except Exception as e:
                logger.warning("STT WebSocket error: %s — reconnecting in 2s", e)
                await asyncio.sleep(2)

    async def _ws_session(self) -> None:
        params = urlencode({
            "language": STT_LANGUAGE,
            "encoding": "linear16",
            "sample_rate": str(STT_SAMPLE_RATE),
            "word_timestamps": "false",
        })
        url = f"{PULSE_BASE_URL}?{params}"
        headers = {"Authorization": f"Bearer {SMALLEST_API_KEY}"}

        async with websockets.connect(url, additional_headers=headers) as ws:
            self._ws = ws
            logger.info("Connected to Pulse STT")

            send_task = asyncio.create_task(self._ws_send_loop(ws))
            recv_task = asyncio.create_task(self._ws_receive_loop(ws))

            try:
                await asyncio.gather(send_task, recv_task)
            finally:
                send_task.cancel()
                recv_task.cancel()

    async def _ws_send_loop(self, ws) -> None:
        """Stream audio chunks to the STT WebSocket."""
        interval = STT_CHUNK_INTERVAL_MS / 1000
        while self._running:
            try:
                chunk = await asyncio.wait_for(self._audio_queue.get(), timeout=interval)
                await ws.send(chunk)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.debug("Send error: %s", e)
                break

    async def _ws_receive_loop(self, ws) -> None:
        """Receive transcripts and process commands."""
        async for message in ws:
            if not self._running:
                break
            try:
                data = json.loads(message)
                transcript = data.get("transcript", "").strip()
                is_final = data.get("is_final", False)
                full_transcript = data.get("full_transcript", "")

                if not transcript:
                    continue

                if self.on_speech_detected and transcript:
                    self.on_speech_detected()

                if is_final:
                    self._process_transcript(full_transcript or transcript)

            except json.JSONDecodeError:
                logger.debug("Non-JSON STT message: %s", message)

    def _process_transcript(self, transcript: str) -> None:
        """Extract command after wake word and fire callback."""
        text = transcript.lower().strip()
        logger.debug("STT transcript: %s", text)

        wake_idx = text.find(WAKE_WORD)
        if wake_idx == -1:
            return

        command = text[wake_idx + len(WAKE_WORD):].strip()
        command = command.lstrip(",").lstrip(".").strip()

        if not command:
            return

        logger.info("Command detected: '%s'", command)
        if self.on_command:
            self.on_command(command)

"""Smallest.ai Lightning V2 Text-to-Speech engine.

Provides async speech synthesis with sub-100ms latency, audio playback
via sounddevice, mid-utterance cancellation for barge-in, and a pyttsx3
fallback if the API is unreachable.
"""

from __future__ import annotations

import asyncio
import io
import logging
import time
import wave
from typing import Optional

import numpy as np
import sounddevice as sd

from config import (
    SMALLEST_API_KEY,
    VOICE_ID,
    TTS_SPEED,
    TTS_SAMPLE_RATE,
    ALERT_VOLUME,
    AlertTier,
)

logger = logging.getLogger("breacher.tts")

# Try importing Smallest.ai SDK
try:
    from smallestai.waves import AsyncWavesClient
    HAS_SMALLEST = True
except ImportError:
    HAS_SMALLEST = False
    logger.warning("smallestai SDK not installed — TTS will use pyttsx3 fallback")

# Fallback
try:
    import pyttsx3
    HAS_PYTTSX3 = True
except ImportError:
    HAS_PYTTSX3 = False


class TTSEngine:
    """Async TTS engine using Smallest.ai Lightning V2 with local fallback."""

    def __init__(self) -> None:
        self._client: Optional[AsyncWavesClient] = None
        self._speaking = False
        self._cancel_requested = False
        self._current_stream: Optional[sd.OutputStream] = None
        self._last_latency_ms: float = 0.0
        self._pyttsx_engine = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        if HAS_SMALLEST and SMALLEST_API_KEY:
            self._client = AsyncWavesClient(api_key=SMALLEST_API_KEY)
            logger.info("Smallest.ai TTS initialized (Lightning V2)")
        elif HAS_PYTTSX3:
            loop = asyncio.get_event_loop()
            self._pyttsx_engine = await loop.run_in_executor(None, pyttsx3.init)
            logger.info("Using pyttsx3 fallback TTS")
        else:
            logger.error("No TTS engine available")

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    @property
    def last_latency_ms(self) -> float:
        return self._last_latency_ms

    async def speak(self, text: str, priority: int = AlertTier.P4_STATUS) -> None:
        """Synthesize and play speech. Blocks until playback completes or is cancelled."""
        if not text.strip():
            return

        async with self._lock:
            self._speaking = True
            self._cancel_requested = False
            volume = ALERT_VOLUME.get(priority, 0.7)

            start = time.time()

            try:
                if self._client:
                    await self._speak_smallest(text, volume)
                elif self._pyttsx_engine:
                    await self._speak_pyttsx(text)
                else:
                    logger.warning("No TTS engine — text: %s", text)
            except Exception as e:
                logger.error("TTS speak failed: %s", e, exc_info=True)
                if self._pyttsx_engine:
                    await self._speak_pyttsx(text)
            finally:
                self._last_latency_ms = (time.time() - start) * 1000
                self._speaking = False

    async def cancel(self) -> None:
        """Cancel current speech immediately (barge-in)."""
        self._cancel_requested = True
        if self._current_stream:
            try:
                self._current_stream.stop()
                self._current_stream.close()
            except Exception:
                pass
            self._current_stream = None
        self._speaking = False
        logger.debug("TTS cancelled (barge-in)")

    # ------------------------------------------------------------------
    # Smallest.ai synthesis
    # ------------------------------------------------------------------

    async def _speak_smallest(self, text: str, volume: float) -> None:
        """Synthesize with Smallest.ai Lightning V2 and play via sounddevice."""
        start = time.time()

        async with self._client as tts:
            audio_bytes = await tts.synthesize(
                text,
                voice_id=VOICE_ID,
                speed=TTS_SPEED,
                sample_rate=TTS_SAMPLE_RATE,
            )

        self._last_latency_ms = (time.time() - start) * 1000
        logger.debug("TTS synthesis: %.0fms for %d chars", self._last_latency_ms, len(text))

        if self._cancel_requested:
            return

        audio_data = self._decode_wav_bytes(audio_bytes)
        if audio_data is None:
            return

        audio_data = (audio_data * volume).astype(np.float32)
        await self._play_audio(audio_data, TTS_SAMPLE_RATE)

    def _decode_wav_bytes(self, raw: bytes) -> Optional[np.ndarray]:
        """Decode WAV/PCM bytes into a numpy float32 array."""
        try:
            buf = io.BytesIO(raw)
            with wave.open(buf, "rb") as wf:
                frames = wf.readframes(wf.getnframes())
                arr = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
                return arr / 32768.0
        except Exception:
            arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
            return arr / 32768.0

    async def _play_audio(self, audio: np.ndarray, sample_rate: int) -> None:
        """Non-blocking audio playback with cancellation support."""
        if self._cancel_requested:
            return

        loop = asyncio.get_event_loop()
        done = asyncio.Event()

        def callback(outdata, frames, time_info, status):
            pass

        try:
            self._current_stream = sd.OutputStream(
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
            )
            self._current_stream.start()

            chunk_size = 4096
            for i in range(0, len(audio), chunk_size):
                if self._cancel_requested:
                    break
                chunk = audio[i:i + chunk_size]
                self._current_stream.write(chunk.reshape(-1, 1))

            if not self._cancel_requested:
                await asyncio.sleep(0.1)  # drain buffer

        except Exception as e:
            logger.error("Audio playback error: %s", e)
        finally:
            if self._current_stream:
                try:
                    self._current_stream.stop()
                    self._current_stream.close()
                except Exception:
                    pass
                self._current_stream = None

    # ------------------------------------------------------------------
    # pyttsx3 fallback
    # ------------------------------------------------------------------

    async def _speak_pyttsx(self, text: str) -> None:
        """Blocking fallback TTS via pyttsx3."""
        if not self._pyttsx_engine:
            return
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._pyttsx_say, text)

    def _pyttsx_say(self, text: str) -> None:
        self._pyttsx_engine.say(text)
        self._pyttsx_engine.runAndWait()

    async def shutdown(self) -> None:
        await self.cancel()
        if self._pyttsx_engine:
            try:
                self._pyttsx_engine.stop()
            except Exception:
                pass

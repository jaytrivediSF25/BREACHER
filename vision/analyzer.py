"""GPT-4o Vision integration for tactical scene analysis.

Captures camera frames, encodes to base64, sends to GPT-4o with a
carefully engineered tactical prompt, and returns structured analysis.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from typing import Optional

import cv2
import numpy as np
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from config import OPENAI_API_KEY, OPENAI_MODEL, CONFIDENCE_THRESHOLD

logger = logging.getLogger("breacher.vision")

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# ---------------------------------------------------------------------------
# Pydantic models for structured GPT-4o output
# ---------------------------------------------------------------------------

class DetectedOccupant(BaseModel):
    id: int
    posture: str = Field(description="STANDING, CROUCHING, or PRONE")
    position_description: str = Field(description="Relative to entry point with compass direction and distance")
    distance_feet: float = Field(description="Estimated distance from entry in feet")
    compass_direction: str = Field(description="N, NE, E, SE, S, SW, W, NW relative to entry")
    hands_visible: bool = True
    hands_obscured: bool = False
    weapon_visible: bool = False
    facing_entry: bool = False
    moving: bool = False
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    visible_items: list[str] = Field(default_factory=list)


class RoomLayout(BaseModel):
    dimensions: str = "Unknown"
    furniture: list[str] = Field(default_factory=list)
    doorways: int = 0
    windows: str = "Unknown"
    cover_positions: list[str] = Field(default_factory=list)
    lighting: str = "Normal"


class ThreatAssessment(BaseModel):
    weapon_detected: bool = False
    movement_toward_entry: bool = False
    overall_threat_level: str = "LOW"
    threat_pct: int = 0


class FrameAnalysis(BaseModel):
    occupants: list[DetectedOccupant] = Field(default_factory=list)
    layout: RoomLayout = Field(default_factory=RoomLayout)
    threats: ThreatAssessment = Field(default_factory=ThreatAssessment)
    timestamp: float = 0.0
    raw_description: str = ""


# ---------------------------------------------------------------------------
# Tactical prompt
# ---------------------------------------------------------------------------

TACTICAL_SYSTEM_PROMPT = """You are a military reconnaissance analyst embedded in an autonomous scout rover. 
You are analyzing camera frames from inside an unknown room during a breach operation.

Your job is to provide precise, actionable intelligence that will be relayed verbally to a Marine fire team waiting outside.

Analyze the image and return a JSON object with EXACTLY this schema:
{
  "occupants": [
    {
      "id": <sequential int starting at 1>,
      "posture": "STANDING" | "CROUCHING" | "PRONE",
      "position_description": "<concise position relative to entry, e.g. 'Behind couch, left side, approximately 10 feet from entry'>",
      "distance_feet": <estimated distance from camera/entry in feet>,
      "compass_direction": "N" | "NE" | "E" | "SE" | "S" | "SW" | "W" | "NW",
      "hands_visible": <boolean>,
      "hands_obscured": <boolean — true if hands are behind furniture or out of frame>,
      "weapon_visible": <boolean>,
      "facing_entry": <boolean — true if facing toward the camera/entry point>,
      "moving": <boolean>,
      "confidence": <0.0 to 1.0>,
      "visible_items": [<list of notable objects near the person>]
    }
  ],
  "layout": {
    "dimensions": "<estimated room dimensions, e.g. '~20 x 15 ft'>",
    "furniture": [<list of furniture items with approximate positions>],
    "doorways": <number of visible doorways/openings>,
    "windows": "<description of windows, e.g. '1 · rear wall · closed'>",
    "cover_positions": [<list of positions that could provide cover>],
    "lighting": "<lighting assessment, e.g. 'Dim — low visibility in NE corner'>"
  },
  "threats": {
    "weapon_detected": <boolean>,
    "movement_toward_entry": <boolean>,
    "overall_threat_level": "LOW" | "MEDIUM" | "HIGH",
    "threat_pct": <0-100 numeric threat assessment>
  }
}

RULES:
- If confidence is below 0.7, say so explicitly in position_description (e.g. "Low confidence — possible person near...").
- Count every person you can see, even partially visible.
- Estimate distances in feet from the camera position (which is the entry point).
- Use compass directions relative to the entry: straight ahead = N, left = W, right = E.
- If you cannot confirm hands are empty, set hands_obscured to true.
- If no people are visible, return an empty occupants array.
- Return ONLY valid JSON. No markdown, no explanation, no code fences."""


class VisionAnalyzer:
    """Sends camera frames to GPT-4o Vision for tactical analysis."""

    def __init__(self) -> None:
        self._last_analysis: Optional[FrameAnalysis] = None
        self._analysis_count: int = 0
        self._total_latency_ms: float = 0

    @property
    def avg_latency_ms(self) -> float:
        if self._analysis_count == 0:
            return 0
        return self._total_latency_ms / self._analysis_count

    async def analyze_frame(self, frame: np.ndarray) -> FrameAnalysis:
        """Send a single camera frame to GPT-4o Vision and parse the response."""
        start = time.time()

        b64 = self._encode_frame(frame)

        try:
            response = await client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": TACTICAL_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64}",
                                    "detail": "high",
                                },
                            },
                            {
                                "type": "text",
                                "text": "Analyze this room. Report all occupants, positions, layout, and threats.",
                            },
                        ],
                    },
                ],
                max_tokens=1500,
                temperature=0.1,
            )

            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            data = json.loads(raw)
            analysis = FrameAnalysis(
                occupants=[DetectedOccupant(**o) for o in data.get("occupants", [])],
                layout=RoomLayout(**data.get("layout", {})),
                threats=ThreatAssessment(**data.get("threats", {})),
                timestamp=time.time(),
                raw_description=raw,
            )

        except json.JSONDecodeError as e:
            logger.error("Failed to parse GPT-4o response as JSON: %s", e)
            analysis = FrameAnalysis(timestamp=time.time(), raw_description=str(e))
        except Exception as e:
            logger.error("Vision analysis failed: %s", e, exc_info=True)
            analysis = FrameAnalysis(timestamp=time.time(), raw_description=str(e))

        elapsed_ms = (time.time() - start) * 1000
        self._total_latency_ms += elapsed_ms
        self._analysis_count += 1
        self._last_analysis = analysis

        logger.info(
            "Vision analysis #%d: %d occupants, threat=%s (%.0fms)",
            self._analysis_count,
            len(analysis.occupants),
            analysis.threats.overall_threat_level,
            elapsed_ms,
        )
        return analysis

    @staticmethod
    def _encode_frame(frame: np.ndarray) -> str:
        """Encode an OpenCV frame as base64 JPEG."""
        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return base64.b64encode(buffer).decode("utf-8")

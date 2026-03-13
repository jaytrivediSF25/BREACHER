"""Persistent in-memory scene state tracker.

Tracks occupants with phonetic callsigns, room layout, threat levels,
and a mission event log for post-mission debrief. Provides change
detection to drive the alert escalation system.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from config import (
    NATO_ALPHABET,
    GREEK_PREFIXES,
    CONFIDENCE_THRESHOLD,
    AlertTier,
)
from vision.analyzer import FrameAnalysis, DetectedOccupant, RoomLayout


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class ChangeType(str, Enum):
    NEW_OCCUPANT = "new_occupant"
    OCCUPANT_REMOVED = "occupant_removed"
    WEAPON_DETECTED = "weapon_detected"
    MOVEMENT_TOWARD_ENTRY = "movement_toward_entry"
    SIGNIFICANT_MOVE = "significant_move"
    MINOR_MOVE = "minor_move"
    POSTURE_CHANGE = "posture_change"
    LAYOUT_UPDATE = "layout_update"
    NO_CHANGE = "no_change"


CHANGE_PRIORITY = {
    ChangeType.WEAPON_DETECTED: AlertTier.P1_CRITICAL,
    ChangeType.MOVEMENT_TOWARD_ENTRY: AlertTier.P1_CRITICAL,
    ChangeType.NEW_OCCUPANT: AlertTier.P2_WARNING,
    ChangeType.OCCUPANT_REMOVED: AlertTier.P2_WARNING,
    ChangeType.SIGNIFICANT_MOVE: AlertTier.P2_WARNING,
    ChangeType.POSTURE_CHANGE: AlertTier.P3_UPDATE,
    ChangeType.MINOR_MOVE: AlertTier.P3_UPDATE,
    ChangeType.LAYOUT_UPDATE: AlertTier.P4_STATUS,
    ChangeType.NO_CHANGE: AlertTier.P4_STATUS,
}


@dataclass
class SceneChange:
    change_type: ChangeType
    priority: AlertTier
    callsign: str = ""
    description: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class TrackedOccupant:
    id: int
    callsign: str
    greek: str
    posture: str = "STANDING"
    position: str = ""
    distance_feet: float = 0.0
    compass_direction: str = "N"
    hands_visible: bool = True
    hands_obscured: bool = False
    weapon_visible: bool = False
    facing_entry: bool = False
    moving: bool = False
    confidence: float = 0.8
    visible_items: list[str] = field(default_factory=list)
    last_seen: float = field(default_factory=time.time)
    first_seen: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "callsign": self.callsign,
            "greek": self.greek,
            "position": self.position,
            "posture": self.posture,
            "distanceFeet": self.distance_feet,
            "compassDirection": self.compass_direction,
            "handsVisible": self.hands_visible,
            "handsObscured": self.hands_obscured,
            "weaponVisible": self.weapon_visible,
            "facingEntry": self.facing_entry,
            "moving": self.moving,
            "confidence": self.confidence,
        }


@dataclass
class MissionEvent:
    event_type: str
    description: str
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Scene Model
# ---------------------------------------------------------------------------

class SceneModel:
    """Central scene state used by all subsystems."""

    def __init__(self) -> None:
        self.occupants: dict[str, TrackedOccupant] = {}
        self.layout: Optional[RoomLayout] = None
        self.rooms: list[RoomLayout] = []
        self.current_room: int = 0
        self.mission_log: list[MissionEvent] = []
        self.threat_level: str = "LOW"
        self.threat_pct: int = 0
        self._next_callsign_idx: int = 0
        self._started_at: float = time.time()

    # ------------------------------------------------------------------
    # Core update
    # ------------------------------------------------------------------

    def update(self, analysis: FrameAnalysis) -> list[SceneChange]:
        """Merge a new frame analysis into the scene state. Returns changes."""
        changes: list[SceneChange] = []

        new_ids = {o.id for o in analysis.occupants}
        existing_ids = set()

        for det in analysis.occupants:
            matched = self._match_occupant(det)
            if matched:
                existing_ids.add(matched.callsign)
                changes.extend(self._update_occupant(matched, det))
            else:
                occ = self._add_occupant(det)
                existing_ids.add(occ.callsign)
                changes.append(SceneChange(
                    change_type=ChangeType.NEW_OCCUPANT,
                    priority=AlertTier.P2_WARNING,
                    callsign=occ.callsign,
                    description=f"New occupant detected: {occ.callsign}. {occ.position}",
                ))

        if analysis.layout and analysis.layout.dimensions != "Unknown":
            if self.layout is None or self.layout.dimensions != analysis.layout.dimensions:
                changes.append(SceneChange(
                    change_type=ChangeType.LAYOUT_UPDATE,
                    priority=AlertTier.P4_STATUS,
                    description="Room layout updated",
                ))
            self.layout = analysis.layout

        self.threat_level = analysis.threats.overall_threat_level
        self.threat_pct = analysis.threats.threat_pct

        if analysis.threats.weapon_detected:
            for occ in self.occupants.values():
                if occ.weapon_visible:
                    changes.append(SceneChange(
                        change_type=ChangeType.WEAPON_DETECTED,
                        priority=AlertTier.P1_CRITICAL,
                        callsign=occ.callsign,
                        description=f"WEAPON VISIBLE on {occ.callsign}, {occ.compass_direction} wall",
                    ))
        if analysis.threats.movement_toward_entry:
            changes.append(SceneChange(
                change_type=ChangeType.MOVEMENT_TOWARD_ENTRY,
                priority=AlertTier.P1_CRITICAL,
                description="Movement detected toward entry point",
            ))

        self._log_event("vision_update", f"{len(analysis.occupants)} occupants, threat={self.threat_level}")

        if not changes:
            changes.append(SceneChange(
                change_type=ChangeType.NO_CHANGE,
                priority=AlertTier.P4_STATUS,
            ))
        return changes

    # ------------------------------------------------------------------
    # Callsign management  (PRD F-VOI-05)
    # ------------------------------------------------------------------

    def _assign_callsign(self) -> tuple[str, str]:
        idx = self._next_callsign_idx
        self._next_callsign_idx += 1
        callsign = NATO_ALPHABET[idx % len(NATO_ALPHABET)]
        greek = GREEK_PREFIXES[idx % len(GREEK_PREFIXES)]
        return callsign.upper(), greek

    def _match_occupant(self, det: DetectedOccupant) -> Optional[TrackedOccupant]:
        """Try to match a detection to an existing tracked occupant by proximity."""
        best: Optional[TrackedOccupant] = None
        best_dist = 5.0  # feet — matching threshold
        for occ in self.occupants.values():
            dist_diff = abs(occ.distance_feet - det.distance_feet)
            same_dir = occ.compass_direction == det.compass_direction
            if dist_diff < best_dist and same_dir:
                best_dist = dist_diff
                best = occ
        return best

    def _add_occupant(self, det: DetectedOccupant) -> TrackedOccupant:
        callsign, greek = self._assign_callsign()
        occ = TrackedOccupant(
            id=det.id,
            callsign=callsign,
            greek=greek,
            posture=det.posture,
            position=det.position_description,
            distance_feet=det.distance_feet,
            compass_direction=det.compass_direction,
            hands_visible=det.hands_visible,
            hands_obscured=det.hands_obscured,
            weapon_visible=det.weapon_visible,
            facing_entry=det.facing_entry,
            moving=det.moving,
            confidence=det.confidence,
            visible_items=det.visible_items,
        )
        self.occupants[callsign] = occ
        self._log_event("new_occupant", f"{callsign} detected at {occ.position}")
        return occ

    def _update_occupant(self, occ: TrackedOccupant, det: DetectedOccupant) -> list[SceneChange]:
        changes: list[SceneChange] = []

        if occ.posture != det.posture:
            changes.append(SceneChange(
                change_type=ChangeType.POSTURE_CHANGE,
                priority=AlertTier.P3_UPDATE,
                callsign=occ.callsign,
                description=f"{occ.callsign} is now {det.posture.lower()}",
            ))

        dist_diff = abs(occ.distance_feet - det.distance_feet)
        if dist_diff > 3.0 or occ.compass_direction != det.compass_direction:
            changes.append(SceneChange(
                change_type=ChangeType.SIGNIFICANT_MOVE,
                priority=AlertTier.P2_WARNING,
                callsign=occ.callsign,
                description=f"{occ.callsign} has moved — now at {det.position_description}",
            ))
        elif dist_diff > 1.0:
            changes.append(SceneChange(
                change_type=ChangeType.MINOR_MOVE,
                priority=AlertTier.P3_UPDATE,
                callsign=occ.callsign,
                description=f"{occ.callsign} shifted position slightly",
            ))

        if det.weapon_visible and not occ.weapon_visible:
            changes.append(SceneChange(
                change_type=ChangeType.WEAPON_DETECTED,
                priority=AlertTier.P1_CRITICAL,
                callsign=occ.callsign,
                description=f"WEAPON VISIBLE on {occ.callsign}",
            ))

        occ.posture = det.posture
        occ.position = det.position_description
        occ.distance_feet = det.distance_feet
        occ.compass_direction = det.compass_direction
        occ.hands_visible = det.hands_visible
        occ.hands_obscured = det.hands_obscured
        occ.weapon_visible = det.weapon_visible
        occ.facing_entry = det.facing_entry
        occ.moving = det.moving
        occ.confidence = det.confidence
        occ.visible_items = det.visible_items
        occ.last_seen = time.time()

        return changes

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_occupant(self, callsign: str) -> Optional[TrackedOccupant]:
        return self.occupants.get(callsign.upper())

    def get_occupant_count(self) -> int:
        return len(self.occupants)

    def get_elapsed(self) -> str:
        """MM:SS since mission start."""
        secs = int(time.time() - self._started_at)
        return f"{secs // 60:02d}:{secs % 60:02d}"

    # ------------------------------------------------------------------
    # Serialization for WebSocket UI
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return the state shape expected by the React Mission Debrief UI."""
        layout = self.layout or RoomLayout()
        cover_str = " / ".join(layout.cover_positions) if layout.cover_positions else "None identified"
        return {
            "occupants": [o.to_dict() for o in self.occupants.values()],
            "room": {
                "dimensions": layout.dimensions,
                "doorways": layout.doorways,
                "windows": layout.windows,
                "cover": cover_str,
                "lighting": layout.lighting,
            },
            "threatLevel": self.threat_level,
            "threatPct": self.threat_pct,
        }

    # ------------------------------------------------------------------
    # Mission log / debrief  (PRD F-VOI-06)
    # ------------------------------------------------------------------

    def _log_event(self, event_type: str, description: str) -> None:
        self.mission_log.append(MissionEvent(
            event_type=event_type,
            description=description,
        ))

    def log_command(self, command: str) -> None:
        self._log_event("command", command)

    def log_tts(self, text: str) -> None:
        self._log_event("tts_output", text)

    def get_debrief(self) -> str:
        """Full mission replay from the event log."""
        lines = ["MISSION DEBRIEF", f"Duration: {self.get_elapsed()}", ""]
        for evt in self.mission_log:
            ts = time.strftime("%H:%M:%S", time.localtime(evt.timestamp))
            lines.append(f"[{ts}] {evt.event_type.upper()}: {evt.description}")
        lines.append("")
        lines.append(f"Total occupants detected: {len(self.occupants)}")
        lines.append(f"Final threat level: {self.threat_level}")
        return "\n".join(lines)

    def reset(self) -> None:
        self.occupants.clear()
        self.layout = None
        self.rooms.clear()
        self.current_room = 0
        self.mission_log.clear()
        self.threat_level = "LOW"
        self.threat_pct = 0
        self._next_callsign_idx = 0
        self._started_at = time.time()

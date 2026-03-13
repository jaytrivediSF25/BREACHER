"""Briefing generator — converts scene model state into tactical speech strings.

Adapts output to the active terminology mode (military, law enforcement,
civilian/SAR) and uses phonetic callsigns consistently.
"""

from __future__ import annotations

from typing import Optional

from config import TerminologyMode, TERMINOLOGY, AlertTier
from vision.scene_model import (
    SceneModel,
    SceneChange,
    ChangeType,
    TrackedOccupant,
)


class BriefingGenerator:
    """Generates natural-language tactical briefings from scene data."""

    def __init__(self, terminology_mode: TerminologyMode = TerminologyMode.MILITARY) -> None:
        self._mode = terminology_mode
        self._terms = TERMINOLOGY[terminology_mode]

    @property
    def mode(self) -> TerminologyMode:
        return self._mode

    def set_mode(self, mode: TerminologyMode) -> None:
        self._mode = mode
        self._terms = TERMINOLOGY[mode]

    # ------------------------------------------------------------------
    # Full sitrep after a sweep
    # ------------------------------------------------------------------

    def initial_sitrep(self, scene: SceneModel) -> str:
        """Complete spoken briefing after a room sweep."""
        parts: list[str] = []
        count = scene.get_occupant_count()

        if count == 0:
            parts.append("Room appears clear. No occupants detected.")
        elif count == 1:
            parts.append("One person in the room.")
        else:
            parts.append(f"{count} people in the room.")

        for occ in scene.occupants.values():
            parts.append(self._describe_occupant(occ))

        layout = scene.layout
        if layout:
            if layout.doorways:
                parts.append(f"{layout.doorways} doorway{'s' if layout.doorways > 1 else ''} detected.")
            if layout.windows and layout.windows != "Unknown":
                parts.append(f"Windows: {layout.windows}.")
            if layout.cover_positions:
                parts.append(f"Cover positions: {', '.join(layout.cover_positions)}.")

        weapons_found = any(o.weapon_visible for o in scene.occupants.values())
        if weapons_found:
            parts.append("WARNING. Weapons visible.")
        else:
            parts.append("No weapons visible.")

        parts.append("Sweep complete.")
        return " ".join(parts)

    # ------------------------------------------------------------------
    # Change alerts
    # ------------------------------------------------------------------

    def change_alert(self, change: SceneChange) -> str:
        """Convert a single scene change into a spoken alert."""
        ct = change.change_type

        if ct == ChangeType.WEAPON_DETECTED:
            return f"ALERT. Weapon visible. {change.callsign}, {change.description}."

        if ct == ChangeType.MOVEMENT_TOWARD_ENTRY:
            return f"ALERT. Movement toward entry. {change.description}."

        if ct == ChangeType.NEW_OCCUPANT:
            return f"New {self._terms['subject'].lower()} detected. {change.callsign}. {change.description}."

        if ct == ChangeType.SIGNIFICANT_MOVE:
            return f"{change.callsign} has moved. {change.description}."

        if ct == ChangeType.POSTURE_CHANGE:
            return f"{change.callsign} {change.description}."

        if ct == ChangeType.MINOR_MOVE:
            return f"{change.callsign} shifted position slightly."

        if ct == ChangeType.OCCUPANT_REMOVED:
            return f"{change.callsign} is no longer visible."

        return change.description or ""

    # ------------------------------------------------------------------
    # Query responses
    # ------------------------------------------------------------------

    def position_query(self, occupant: TrackedOccupant) -> str:
        """Respond to 'where is [callsign]?'"""
        posture = occupant.posture.lower()
        pos = occupant.position
        dist = f"approximately {occupant.distance_feet:.0f} feet from entry"

        hands = ""
        if occupant.hands_obscured:
            hands = " Hands are partially obscured."
        elif occupant.hands_visible:
            hands = " Hands are visible and appear empty."

        if occupant.confidence < 0.7:
            confidence_note = " Low confidence on this reading."
        else:
            confidence_note = ""

        return (
            f"{occupant.callsign} is {posture}, {pos}, {dist}. "
            f"Has not moved since last update.{hands}{confidence_note}"
        )

    def threat_query(self, scene: SceneModel) -> str:
        """Respond to 'any weapons?' or 'threats?'"""
        armed = [o for o in scene.occupants.values() if o.weapon_visible]
        obscured = [o for o in scene.occupants.values() if o.hands_obscured]

        if armed:
            names = ", ".join(o.callsign for o in armed)
            return f"Weapons detected on {names}. Threat level {scene.threat_level}."

        parts = ["No weapons detected on any subject."]
        if obscured:
            names = ", ".join(o.callsign for o in obscured)
            parts.append(f"Hands obscured on {names}. Cannot fully confirm.")
        parts.append(f"Threat level {scene.threat_level}.")
        return " ".join(parts)

    def status_report(self, battery: int, sweep_pct: float, scene: SceneModel) -> str:
        """Respond to 'status'."""
        return (
            f"Battery at {battery} percent. "
            f"Sweep {sweep_pct:.0f} percent complete. "
            f"{scene.get_occupant_count()} occupants tracked. "
            f"Threat level {scene.threat_level}."
        )

    def full_debrief(self, scene: SceneModel) -> str:
        """Respond to 'debrief'."""
        return scene.get_debrief()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _describe_occupant(self, occ: TrackedOccupant) -> str:
        """Build a spoken description for one occupant."""
        subject = self._terms["subject"]
        posture = occ.posture.lower()
        pos = occ.position
        dist = f"approximately {occ.distance_feet:.0f} feet"

        if self._mode == TerminologyMode.MILITARY:
            line = f"{occ.callsign}. {posture.capitalize()}, {pos}, {dist} from entry."
        elif self._mode == TerminologyMode.LAW_ENFORCEMENT:
            line = f"{subject} {occ.callsign}. {posture.capitalize()} {pos}, {dist} from entry."
        else:
            line = f"One person found {pos}, {dist} from entry. They appear to be {posture}."

        if occ.hands_obscured:
            line += f" Hands partially obscured — cannot fully confirm."
        elif not occ.hands_visible:
            line += f" Hands not visible."
        if occ.weapon_visible:
            line += f" WARNING — weapon visible."
        if occ.facing_entry:
            line += f" Facing toward entry."

        return line

    def sweep_progress(self, pct: float) -> str:
        return f"Sweep {pct:.0f} percent complete."

    def doorway_detected(self) -> str:
        return "I see another doorway. Awaiting your command to continue."

    def ready_confirmation(self) -> str:
        return "Ready. Awaiting entry."

    def deploy_confirmation(self) -> str:
        return "Copy. Entering now."

    def abort_confirmation(self) -> str:
        return "Aborting. All stop."

    def hold_confirmation(self) -> str:
        return "Holding position."

    def recall_confirmation(self) -> str:
        return "Returning to entry point."

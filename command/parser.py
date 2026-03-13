"""Voice command parser — converts transcribed speech into system actions.

Implements the full command vocabulary from PRD Sections 5.3/5.4 using
keyword matching first (fast, reliable) with a GPT fallback for
ambiguous commands.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from config import (
    MissionProfile,
    TerminologyMode,
    AlertTier,
    NATO_ALPHABET,
)

logger = logging.getLogger("breacher.command")


class Intent(str, Enum):
    PREPARE = "prepare"
    DEPLOY = "deploy"
    ABORT = "abort"
    HALT = "halt"
    CONTINUE = "continue"
    DIRECTIONAL = "directional"
    QUERY_POSITION = "query_position"
    QUERY_THREAT = "query_threat"
    STATUS = "status"
    ROVER_POSITION = "rover_position"
    REPORT = "report"
    DEBRIEF = "debrief"
    SET_PROFILE = "set_profile"
    SET_TERMINOLOGY = "set_terminology"
    RECALL = "recall"
    SWEEP = "sweep"
    SITREP = "sitrep"
    UNKNOWN = "unknown"


@dataclass
class Command:
    intent: Intent
    raw_text: str
    target: str = ""        # callsign, direction, profile name, etc.
    confidence: float = 1.0


# ---------------------------------------------------------------------------
# Keyword patterns (ordered by priority — abort is checked first)
# ---------------------------------------------------------------------------

KEYWORD_PATTERNS: list[tuple[list[str], Intent, Optional[str]]] = [
    # ABORT — highest priority, always processed
    (["abort", "emergency stop", "all stop"], Intent.ABORT, None),

    # Deployment
    (["prepare to deploy", "prepare", "get ready"], Intent.PREPARE, None),
    (["go", "enter", "deploy", "breach", "send it"], Intent.DEPLOY, None),

    # Movement
    (["hold", "stop", "freeze", "pause"], Intent.HALT, None),
    (["continue", "proceed", "go through", "push through"], Intent.CONTINUE, None),
    (["come back", "return", "recall", "pull back", "come home"], Intent.RECALL, None),

    # Sweep
    (["sweep", "scan", "search"], Intent.SWEEP, None),
    (["sitrep", "sit rep", "situation report", "what do you see"], Intent.SITREP, None),

    # Queries
    (["any weapons", "weapons", "threats", "armed", "threat level"], Intent.QUERY_THREAT, None),
    (["status", "how much battery", "battery"], Intent.STATUS, None),
    (["where are you", "your position", "your location"], Intent.ROVER_POSITION, None),
    (["report"], Intent.REPORT, None),
    (["debrief", "mission replay", "after action"], Intent.DEBRIEF, None),

    # Profile & terminology
    (["set profile", "switch profile"], Intent.SET_PROFILE, None),
    (["switch to", "change to", "use mode"], Intent.SET_TERMINOLOGY, None),

    # Directional — checked last since it's a broad match
    (["check behind", "look at", "go to", "investigate", "check the",
      "go left", "go right", "turn left", "turn right", "go back"], Intent.DIRECTIONAL, None),
]

CALLSIGN_LOWER = [c.lower() for c in NATO_ALPHABET]


class CommandParser:
    """Parse transcribed voice commands into structured Command objects."""

    def parse(self, transcript: str) -> Command:
        """Match transcript against keyword patterns."""
        text = transcript.lower().strip()

        # Always check abort first
        if any(kw in text for kw in ["abort", "emergency", "all stop"]):
            return Command(intent=Intent.ABORT, raw_text=transcript)

        # Position query — special handling for "where is [callsign]"
        where_match = re.search(r"where\s+is\s+(\w+)", text)
        if where_match:
            target = where_match.group(1)
            if target in CALLSIGN_LOWER:
                return Command(
                    intent=Intent.QUERY_POSITION,
                    raw_text=transcript,
                    target=target.upper(),
                )
            elif target in ("he", "she", "the", "that"):
                return Command(intent=Intent.QUERY_POSITION, raw_text=transcript, target="LAST")

        # Profile switching
        profile_match = re.search(r"set profile\s+(.+)", text)
        if profile_match:
            return Command(
                intent=Intent.SET_PROFILE,
                raw_text=transcript,
                target=profile_match.group(1).strip(),
            )

        # Terminology switching
        term_match = re.search(r"switch to\s+(\w+)\s+mode", text)
        if term_match:
            return Command(
                intent=Intent.SET_TERMINOLOGY,
                raw_text=transcript,
                target=term_match.group(1).strip(),
            )

        for keywords, intent, _ in KEYWORD_PATTERNS:
            if any(kw in text for kw in keywords):
                target = ""
                if intent == Intent.DIRECTIONAL:
                    target = self._extract_direction(text)
                elif intent == Intent.QUERY_POSITION:
                    target = self._extract_callsign(text)
                return Command(intent=intent, raw_text=transcript, target=target)

        return Command(intent=Intent.UNKNOWN, raw_text=transcript, confidence=0.3)

    async def execute(self, command: Command, ctx: "BreacherContext") -> None:
        """Execute a parsed command against the system context."""
        intent = command.intent
        logger.info("Executing command: %s (target=%s)", intent, command.target)

        ctx.scene_model.log_command(f"{intent.value}: {command.raw_text}")

        if intent == Intent.ABORT:
            await ctx.nav.abort()
            ctx.alert_mgr.flush()
            await ctx.alert_mgr.enqueue(
                ctx.briefing.abort_confirmation(), AlertTier.P1_CRITICAL
            )

        elif intent == Intent.PREPARE:
            await ctx.alert_mgr.enqueue(
                ctx.briefing.ready_confirmation(), AlertTier.P4_STATUS
            )

        elif intent == Intent.DEPLOY:
            await ctx.alert_mgr.enqueue(
                ctx.briefing.deploy_confirmation(), AlertTier.P4_STATUS
            )
            if ctx.on_deploy:
                await ctx.on_deploy()

        elif intent == Intent.HALT:
            await ctx.nav.pause()
            await ctx.alert_mgr.enqueue(
                ctx.briefing.hold_confirmation(), AlertTier.P4_STATUS
            )

        elif intent == Intent.CONTINUE:
            await ctx.nav.continue_through_doorway()

        elif intent == Intent.RECALL:
            await ctx.alert_mgr.enqueue(
                ctx.briefing.recall_confirmation(), AlertTier.P4_STATUS
            )
            asyncio.create_task(ctx.nav.return_to_entry())

        elif intent == Intent.SWEEP:
            if ctx.on_deploy:
                await ctx.on_deploy()

        elif intent == Intent.SITREP:
            sitrep = ctx.briefing.initial_sitrep(ctx.scene_model)
            await ctx.alert_mgr.enqueue(sitrep, AlertTier.P2_WARNING)

        elif intent == Intent.QUERY_POSITION:
            callsign = command.target
            occ = ctx.scene_model.get_occupant(callsign)
            if occ:
                msg = ctx.briefing.position_query(occ)
                await ctx.alert_mgr.enqueue(msg, AlertTier.P3_UPDATE)
            else:
                await ctx.alert_mgr.enqueue(
                    f"No occupant with callsign {callsign} currently tracked.",
                    AlertTier.P3_UPDATE,
                )

        elif intent == Intent.QUERY_THREAT:
            msg = ctx.briefing.threat_query(ctx.scene_model)
            await ctx.alert_mgr.enqueue(msg, AlertTier.P2_WARNING)

        elif intent == Intent.STATUS:
            battery = await ctx.rover.get_battery()
            msg = ctx.briefing.status_report(battery, ctx.nav.sweep_pct, ctx.scene_model)
            await ctx.alert_mgr.enqueue(msg, AlertTier.P4_STATUS)

        elif intent == Intent.ROVER_POSITION:
            pos_desc = await ctx.rover.get_position_description()
            await ctx.alert_mgr.enqueue(pos_desc, AlertTier.P4_STATUS)

        elif intent == Intent.REPORT:
            sitrep = ctx.briefing.initial_sitrep(ctx.scene_model)
            await ctx.alert_mgr.enqueue(sitrep, AlertTier.P2_WARNING)

        elif intent == Intent.DEBRIEF:
            debrief = ctx.briefing.full_debrief(ctx.scene_model)
            await ctx.alert_mgr.enqueue(debrief, AlertTier.P3_UPDATE)

        elif intent == Intent.DIRECTIONAL:
            await ctx.nav.redirect(command.target or command.raw_text)

        elif intent == Intent.SET_PROFILE:
            try:
                profile = MissionProfile(command.target.replace(" ", "_"))
                ctx.mission_profile = profile
                await ctx.alert_mgr.enqueue(
                    f"Profile set to {profile.value.replace('_', ' ')}.",
                    AlertTier.P4_STATUS,
                )
            except ValueError:
                await ctx.alert_mgr.enqueue(
                    f"Unknown profile: {command.target}.", AlertTier.P4_STATUS
                )

        elif intent == Intent.SET_TERMINOLOGY:
            try:
                mode = TerminologyMode(command.target)
                ctx.briefing.set_mode(mode)
                await ctx.alert_mgr.enqueue(
                    f"Switched to {mode.value.replace('_', ' ')} mode.",
                    AlertTier.P4_STATUS,
                )
            except ValueError:
                await ctx.alert_mgr.enqueue(
                    f"Unknown mode: {command.target}.", AlertTier.P4_STATUS
                )

        elif intent == Intent.UNKNOWN:
            logger.warning("Unknown command: %s", command.raw_text)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_direction(text: str) -> str:
        for phrase in ["check behind the", "check behind", "look at the",
                       "go to the", "investigate the", "check the"]:
            if phrase in text:
                return text.split(phrase, 1)[1].strip()
        if "left" in text:
            return "left"
        if "right" in text:
            return "right"
        if "back" in text:
            return "back"
        return text

    @staticmethod
    def _extract_callsign(text: str) -> str:
        for cs in CALLSIGN_LOWER:
            if cs in text:
                return cs.upper()
        return ""


@dataclass
class BreacherContext:
    """Shared context passed to command execution."""
    rover: object
    nav: object
    scene_model: object
    alert_mgr: object
    briefing: object
    tts: object = None
    mission_profile: MissionProfile = MissionProfile.STANDARD_CLEARANCE
    on_deploy: Optional[object] = None

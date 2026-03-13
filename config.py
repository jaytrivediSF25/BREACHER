import os
from enum import Enum, IntEnum
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# API Keys & Connection
# ---------------------------------------------------------------------------
CYBERWAVE_API_TOKEN = os.getenv("CYBERWAVE_API_TOKEN", "")
SMALLEST_API_KEY = os.getenv("SMALLEST_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ROVER_TWIN_ID = os.getenv("ROVER_TWIN_ID", "")
VOICE_ID = os.getenv("VOICE_ID", "emily")

# ---------------------------------------------------------------------------
# Mission Profiles  (PRD F-OPR-01)
# ---------------------------------------------------------------------------

class MissionProfile(str, Enum):
    STANDARD_CLEARANCE = "standard_clearance"
    QUICK_SCAN = "quick_scan"
    SILENT = "silent"
    CONTINUOUS_PATROL = "continuous_patrol"

MISSION_PROFILE = MissionProfile(
    os.getenv("MISSION_PROFILE", MissionProfile.STANDARD_CLEARANCE.value)
)

PROFILE_CONFIG = {
    MissionProfile.STANDARD_CLEARANCE: {
        "autonomous_sweep": True,
        "tts_enabled": True,
        "narrate_layout": True,
        "loop": False,
    },
    MissionProfile.QUICK_SCAN: {
        "autonomous_sweep": True,
        "tts_enabled": True,
        "narrate_layout": False,
        "loop": False,
    },
    MissionProfile.SILENT: {
        "autonomous_sweep": True,
        "tts_enabled": False,
        "narrate_layout": True,
        "loop": False,
    },
    MissionProfile.CONTINUOUS_PATROL: {
        "autonomous_sweep": True,
        "tts_enabled": True,
        "narrate_layout": False,
        "loop": True,
    },
}

# ---------------------------------------------------------------------------
# Terminology Modes  (PRD F-OPR-03)
# ---------------------------------------------------------------------------

class TerminologyMode(str, Enum):
    MILITARY = "military"
    LAW_ENFORCEMENT = "law_enforcement"
    CIVILIAN_SAR = "civilian_sar"

TERMINOLOGY_MODE = TerminologyMode(
    os.getenv("TERMINOLOGY_MODE", TerminologyMode.MILITARY.value)
)

TERMINOLOGY = {
    TerminologyMode.MILITARY: {
        "subject": "Subject",
        "position_style": "compass",      # "northwest sector"
        "cover": "hard cover",
        "weapon_alert": "Weapon visible",
    },
    TerminologyMode.LAW_ENFORCEMENT: {
        "subject": "Suspect",
        "position_style": "relative",      # "back-left corner"
        "cover": "couch",
        "weapon_alert": "Weapon detected",
    },
    TerminologyMode.CIVILIAN_SAR: {
        "subject": "Person",
        "position_style": "relative",
        "cover": "furniture",
        "weapon_alert": "Possible weapon",
    },
}

# ---------------------------------------------------------------------------
# Alert Tiers  (PRD F-VOI-04)
# ---------------------------------------------------------------------------

class AlertTier(IntEnum):
    P1_CRITICAL = 1   # Weapon / movement toward entry
    P2_WARNING = 2    # New occupant / significant movement
    P3_UPDATE = 3     # Minor positional shift
    P4_STATUS = 4     # Sweep progress, battery, routine

ALERT_VOLUME = {
    AlertTier.P1_CRITICAL: 1.0,
    AlertTier.P2_WARNING: 0.8,
    AlertTier.P3_UPDATE: 0.7,
    AlertTier.P4_STATUS: 0.6,
}

# ---------------------------------------------------------------------------
# Phonetic Callsigns  (PRD F-VOI-05)
# ---------------------------------------------------------------------------
NATO_ALPHABET = [
    "Alpha", "Bravo", "Charlie", "Delta", "Echo",
    "Foxtrot", "Golf", "Hotel", "India", "Juliet",
    "Kilo", "Lima", "Mike", "November", "Oscar",
    "Papa", "Quebec", "Romeo", "Sierra", "Tango",
    "Uniform", "Victor", "Whiskey", "X-ray", "Yankee", "Zulu",
]

GREEK_PREFIXES = [
    "\u03b1", "\u03b2", "\u03b3", "\u03b4", "\u03b5",
    "\u03b6", "\u03b7", "\u03b8", "\u03b9", "\u03ba",
]

# ---------------------------------------------------------------------------
# Vision
# ---------------------------------------------------------------------------
FRAME_RATE = 2                     # fps sent to GPT-4o
CONFIDENCE_THRESHOLD = 0.7
OPENAI_MODEL = "gpt-4o"

# ---------------------------------------------------------------------------
# Voice Timing
# ---------------------------------------------------------------------------
TTS_LATENCY_TARGET_MS = 100
TTS_SPEED = 1.0
TTS_SAMPLE_RATE = 24000

STT_CHUNK_SIZE = 4096              # bytes per chunk
STT_CHUNK_INTERVAL_MS = 75         # send interval
STT_SAMPLE_RATE = 16000
STT_LANGUAGE = "en"

# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------
SWEEP_DIRECTION = "clockwise"
SWEEP_STEP_CM = 20                 # forward step per iteration
TURN_STEP_DEG = 90                 # turn increment
USE_DEMO_SWEEP = True              # use scripted demo_sweep for hackathon reliability

# ---------------------------------------------------------------------------
# WebSocket Server (UI bridge)
# ---------------------------------------------------------------------------
WS_HOST = "localhost"
WS_PORT = 8765

# ---------------------------------------------------------------------------
# Mission States
# ---------------------------------------------------------------------------

class MissionState(str, Enum):
    STANDBY = "standby"
    READY = "ready"
    DEPLOYED = "deployed"
    SWEEPING = "sweeping"
    QUERYING = "querying"
    COMPLETE = "complete"
    DEBRIEF = "debrief"
    ABORTED = "aborted"

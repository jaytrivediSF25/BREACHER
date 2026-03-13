# BREACHER — Tactical AI Scout Rover

**Voice-first autonomous tactical intelligence system** built on the UGV Beast Rover. BREACHER enters unknown rooms before personnel, scans with GPT-4o Vision, and delivers real-time spoken briefings through Smallest.ai — no screen, no controller, just a voice in your ear telling you what is on the other side of the door.

> *"This screen is for the judges. The Marines don't look at it. They just listen."*

---

## Architecture

```
┌──────────────┐    ┌───────────────┐    ┌──────────────────┐
│  Microphone   │───▶│ Smallest.ai   │───▶│ Command Parser   │
│  (Operator)   │    │ Pulse STT     │    │ Intent Router    │
└──────────────┘    └───────────────┘    └────────┬─────────┘
                                                   │
          ┌────────────────────────────────────────┘
          ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────┐
│ Cyberwave SDK    │───▶│ GPT-4o Vision    │───▶│ Scene Model   │
│ Beast Rover      │    │ Tactical Prompt  │    │ (Occupants,   │
│ Motor + Camera   │    │ 2fps Analysis    │    │  Layout,      │
└──────────────────┘    └──────────────────┘    │  Threats)     │
                                                 └──────┬───────┘
                                                        │
                                                        ▼
                                                 ┌──────────────┐
                                                 │ Alert Manager │
                                                 │ Priority Queue│
                                                 └──────┬───────┘
                                                        │
          ┌─────────────────────────────────────────────┘
          ▼                          ▼
┌──────────────────┐    ┌──────────────────────┐
│ Smallest.ai TTS  │    │ WebSocket Server     │
│ Lightning V2     │    │ ws://localhost:8765   │
│ <100ms Latency   │    │ → React Dashboard    │
└──────┬───────────┘    └──────────────────────┘
       ▼
┌──────────────┐
│  Earpiece    │
│  (Operator)  │
└──────────────┘
```

---

## Quick Start

### 1. Environment Setup

```bash
cd breacher

# Copy and fill in your API keys
cp .env.example .env
# Edit .env with:
#   CYBERWAVE_API_TOKEN=your_token
#   SMALLEST_API_KEY=your_key
#   OPENAI_API_KEY=your_key
#   ROVER_TWIN_ID=your_rover_twin_id
```

### 2. Python Backend

```bash
pip install -r requirements.txt
python main.py
```

The backend starts:
- All 4 async threads (vision, TTS, STT, navigation)
- WebSocket server on `ws://localhost:8765`
- STT listening on default microphone

### 3. React Dashboard

```bash
cd ui
npm install
npm run dev
```

Opens at `http://localhost:3000`. Shows mock data immediately; switches to live data when the Python backend is running.

---

## Voice Commands

| Command | What It Does |
|---------|-------------|
| *"Breacher, prepare to deploy"* | Enter ready state |
| *"Breacher, go"* | Start autonomous room sweep |
| *"Breacher, hold"* | Pause rover and sweep |
| *"Breacher, continue"* | Proceed through detected doorway |
| *"Breacher, abort"* | Emergency stop (highest priority) |
| *"Breacher, where is Alpha?"* | Get position of specific subject |
| *"Breacher, any weapons?"* | Threat assessment query |
| *"Breacher, status"* | Battery, sweep %, occupant count |
| *"Breacher, sitrep"* | Full situation report |
| *"Breacher, debrief"* | Post-mission replay |
| *"Breacher, return"* | Navigate back to entry point |
| *"Breacher, check behind the couch"* | Redirect to specific area |

---

## Demo Script (Hackathon Judges)

### Setup
Place 2 teammates inside the demo room. One crouching behind a table. One standing near a wall. Do NOT tell the judges what is in the room.

### Pitch (30 seconds)
> *"Imagine you are a Marine. You are stacked outside a door in Kandahar. You have no idea who is in that room or where they are. You could open the door and find out — and maybe get shot doing it. Or you could send Breacher in first."*

### Demo
```
[PRESENTER]   "Breacher, go."
              → Rover enters autonomously. 15-20 seconds of sweep.
[BREACHER]    "Two people in the room. Alpha is crouching behind the
               table, back-left corner — about 12 feet from you.
               Bravo is standing near the right wall, 15 feet in.
               No weapons visible."
              → Let it land.
[PRESENTER]   "Breacher, where is Bravo?"
[BREACHER]    "Bravo is on the right wall, standing, approximately
               15 feet from entry. Facing toward the door. Has not
               moved since I first spotted them."
[PRESENTER]   "Any threats?"
[BREACHER]    "No weapons detected on either subject. Alpha's hands
               are partially out of frame — I cannot fully confirm.
               Recommend verification."
```

> *"That team just went from blind to briefed in 20 seconds. They know the count, the positions, the layout, and the threat level — and they never took their hands off their rifles. That is BREACHER."*

---

## Prize Tracks

| Track | How BREACHER Qualifies |
|-------|----------------------|
| **Cyberwave Grand Prize** | 100% of locomotion, camera, and sensors through Cyberwave SDK |
| **Cyberwave Best Locomotion** | Autonomous room sweep, obstacle avoidance, multi-room clearance |
| **Smallest.ai Grand Prize** | STT handles all commands, TTS delivers all intelligence output |

---

## Project Structure

```
breacher/
  main.py              — Async orchestrator + WebSocket server
  config.py            — All configuration and constants
  rover/
    controller.py      — Cyberwave SDK wrapper
    navigation.py      — Clockwise wall-follow sweep
  vision/
    analyzer.py        — GPT-4o Vision tactical analysis
    scene_model.py     — Occupant tracking + scene state
  voice/
    tts.py             — Smallest.ai Lightning V2 TTS
    stt.py             — Smallest.ai Pulse STT
    alert_manager.py   — 4-tier priority queue
    briefing.py        — Scene-to-speech generator
  command/
    parser.py          — Voice command parsing
  ui/                  — React + Tailwind dashboard
    src/
      App.jsx          — Root layout (3-column grid)
      components/      — 9 panel components
      hooks/           — WebSocket + mock data
      constants/       — Colors + mock state
```

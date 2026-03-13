export const MOCK_SCENE_STATE = {
  occupants: [
    {
      id: 1,
      callsign: 'ALPHA',
      position: 'Prone behind couch, NW corner, ~10ft',
      posture: 'PRONE',
      handsVisible: true,
      weaponVisible: false,
      facingEntry: false,
      handsObscured: false,
      moving: false,
    },
    {
      id: 2,
      callsign: 'BRAVO',
      position: 'Standing, kitchen doorway, left wall, ~20ft',
      posture: 'STANDING',
      handsVisible: true,
      weaponVisible: false,
      facingEntry: true,
      handsObscured: false,
      moving: false,
    },
  ],
  room: {
    dimensions: '~20 x 15 ft',
    doorways: 2,
    windows: '1 · rear wall · closed',
    cover: 'Couch / Table',
    lighting: 'Dim — low confidence NE corner',
  },
  threatLevel: 'LOW',
  threatPct: 15,
  sweepPct: 80,
  quadrants: { NW: 'done', NE: 'done', SW: 'done', SE: 'active' },
  roverPosition: { x: 50, y: 87 },
  roverPath: [
    [50, 90], [50, 20], [15, 20], [15, 80],
    [85, 80], [85, 20], [50, 20],
  ],
  latencyMs: 87,
  fpsCurrent: 2.4,
  batteryPct: 78,
  ttsActive: true,
}

export const MOCK_VOICE_LOG = [
  { speaker: 'OPERATOR', text: 'Breacher, go.', ts: '00:03' },
  {
    speaker: 'BREACHER',
    text: 'Copy. Entering now. Two people in the room. Alpha is prone behind the couch, left side, ten feet. Bravo is standing in the kitchen doorway, twenty feet. No weapons visible.',
    ts: '00:18',
  },
  { speaker: 'OPERATOR', text: 'Where is Bravo exactly?', ts: '00:24' },
  {
    speaker: 'BREACHER',
    text: 'Bravo is in the kitchen doorway, left wall, standing, eighteen feet from entry. Has not moved. Hands are visible and empty.',
    ts: '00:25',
  },
]

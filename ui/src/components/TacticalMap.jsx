import { COLORS } from '../constants/colors'

const SUBJECT_COLORS = [
  'rgba(192,57,43,0.8)',   // ALPHA — red
  'rgba(230,126,34,0.8)',  // BRAVO — amber
  'rgba(149,165,166,0.8)', // CHARLIE+ — gray
]

export default function TacticalMap({ sceneState }) {
  const {
    roverPosition = { x: 50, y: 50 },
    roverPath = [],
    occupants = [],
  } = sceneState || {}

  const pathStr = roverPath.map(p => `${p[0]},${p[1]}`).join(' ')

  return (
    <div style={{ background: COLORS.panel }}>
      <div className="px-3 pt-2 pb-1">
        <span className="uppercase tracking-widest" style={{ fontSize: 10, color: COLORS.textDim }}>
          TACTICAL MAP // ROVER POV
        </span>
      </div>

      <div className="px-2 pb-1">
        <svg
          viewBox="0 0 100 100"
          className="w-full"
          style={{
            aspectRatio: '1/1',
            background: `${COLORS.panelDeep}`,
            backgroundImage:
              'repeating-linear-gradient(rgba(255,255,255,0.025) 0 1px, transparent 1px 20%), ' +
              'repeating-linear-gradient(90deg, rgba(255,255,255,0.025) 0 1px, transparent 1px 20%)',
          }}
        >
          {/* Room walls */}
          <rect x="5" y="5" width="90" height="90" fill="none" stroke="#2a2a2a" strokeWidth="0.5" />

          {/* Kitchen (inner room) */}
          <rect x="5" y="5" width="35" height="45" fill="none" stroke="#1a1a1a" strokeWidth="0.3" />
          <text x="15" y="28" fill="#333" fontSize="3" fontFamily="'Courier New'">KITCHEN</text>

          {/* Furniture */}
          <rect x="15" y="60" width="20" height="8" fill="#111" stroke="#1a1a1a" strokeWidth="0.3" />
          <text x="17" y="66" fill="#222" fontSize="2.5" fontFamily="'Courier New'">COUCH</text>

          <rect x="60" y="55" width="12" height="12" fill="#111" stroke="#1a1a1a" strokeWidth="0.3" />
          <text x="61" y="63" fill="#222" fontSize="2.5" fontFamily="'Courier New'">TABLE</text>

          {/* Entry point marker */}
          <line x1="45" y1="95" x2="55" y2="95" stroke={COLORS.accent} strokeWidth="1" opacity="0.5" />
          <text x="42" y="99" fill="#444" fontSize="2.5" fontFamily="'Courier New'">ENTRY</text>

          {/* Sweep path */}
          {roverPath.length > 1 && (
            <polyline
              points={pathStr}
              fill="none"
              stroke={COLORS.accent}
              strokeWidth="0.5"
              strokeDasharray="2 1.5"
              opacity="0.4"
            />
          )}

          {/* Subject dots */}
          {occupants.map((occ, i) => {
            const sx = i === 0 ? 25 : 22
            const sy = i === 0 ? 64 : 28
            const color = SUBJECT_COLORS[i] || SUBJECT_COLORS[2]
            return (
              <g key={occ.id}>
                <circle cx={sx} cy={sy} r="2" fill={color} />
                <text x={sx} y={sy - 4} fill={color} fontSize="3" fontFamily="'Courier New'" textAnchor="middle">
                  {occ.callsign}
                </text>
              </g>
            )
          })}

          {/* Rover dot */}
          <circle cx={roverPosition.x} cy={roverPosition.y} r="2.5" fill={COLORS.accent} />
          <circle cx={roverPosition.x} cy={roverPosition.y} r="5" fill="none" stroke={COLORS.accent} strokeWidth="0.3" opacity="0.5">
            <animate attributeName="r" values="5;11;5" dur="2s" repeatCount="indefinite" />
            <animate attributeName="opacity" values="0.5;0;0.5" dur="2s" repeatCount="indefinite" />
          </circle>
        </svg>

        {/* Legend */}
        <div className="flex gap-4 px-1 py-1">
          {[
            { label: 'ROVER', color: COLORS.accent },
            { label: 'ALPHA', color: 'rgba(192,57,43,0.7)' },
            { label: 'BRAVO', color: 'rgba(230,126,34,0.7)' },
          ].map(item => (
            <div key={item.label} className="flex items-center gap-1">
              <span className="inline-block" style={{ width: 6, height: 6, background: item.color }} />
              <span className="uppercase tracking-widest" style={{ fontSize: 9, color: COLORS.textDim }}>
                {item.label}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

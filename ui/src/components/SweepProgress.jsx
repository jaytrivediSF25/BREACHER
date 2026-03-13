import { COLORS } from '../constants/colors'

const R = 36
const CIRCUMFERENCE = 2 * Math.PI * R
const QUADRANT_LABELS = ['NW', 'NE', 'SW', 'SE']

export default function SweepProgress({ sweepPct = 0, quadrants = {} }) {
  const offset = CIRCUMFERENCE * (1 - sweepPct / 100)

  return (
    <div className="flex flex-col items-center" style={{ background: COLORS.panel }}>
      <div className="w-full px-3 pt-2 pb-1">
        <span className="uppercase tracking-widest" style={{ fontSize: 10, color: COLORS.textDim }}>
          SWEEP COVERAGE
        </span>
      </div>

      {/* Circular ring */}
      <svg width="100" height="100" viewBox="0 0 100 100" className="mt-1">
        <circle
          cx="50" cy="50" r={R}
          fill="none" stroke={COLORS.borderFaint} strokeWidth="4"
        />
        <circle
          cx="50" cy="50" r={R}
          fill="none" stroke={COLORS.accent} strokeWidth="4"
          strokeLinecap="round"
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={offset}
          transform="rotate(-90 50 50)"
          style={{ transition: 'stroke-dashoffset 0.5s ease' }}
        />
        <text
          x="50" y="48" textAnchor="middle" dominantBaseline="central"
          fill={COLORS.textPrimary} fontSize="16" fontWeight="bold"
          fontFamily="'Courier New'"
        >
          {Math.round(sweepPct)}%
        </text>
        <text
          x="50" y="60" textAnchor="middle"
          fill={COLORS.textDim} fontSize="7"
          fontFamily="'Courier New'" letterSpacing="2"
        >
          SWEEP
        </text>
      </svg>

      {/* Quadrant indicators */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 mt-2 mb-2">
        {QUADRANT_LABELS.map(q => {
          const state = quadrants[q] || 'pending'
          let color = COLORS.textGhost
          let suffix = ''
          if (state === 'done') { color = COLORS.textDim; suffix = ' \u2713' }
          if (state === 'active') { color = COLORS.accent; suffix = ' \u00b7\u00b7\u00b7' }
          return (
            <span
              key={q}
              className="uppercase tracking-widest font-mono"
              style={{ fontSize: 9, color }}
            >
              {q}{suffix}
            </span>
          )
        })}
      </div>
    </div>
  )
}

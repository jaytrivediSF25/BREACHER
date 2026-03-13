import { useState, useEffect } from 'react'
import { COLORS } from '../constants/colors'

export default function CameraFeed({ occupants = [], fpsCurrent = 2.4 }) {
  const [ts, setTs] = useState('')

  useEffect(() => {
    const tick = () => {
      const d = new Date()
      setTs(
        d.getHours().toString().padStart(2, '0') + ':' +
        d.getMinutes().toString().padStart(2, '0') + ':' +
        d.getSeconds().toString().padStart(2, '0')
      )
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])

  const bboxColors = [COLORS.accent, COLORS.warning, COLORS.textMuted]

  return (
    <div className="relative w-full" style={{ aspectRatio: '16/9', background: COLORS.bg }}>
      {/* Scan line */}
      <div
        className="absolute left-0 w-full animate-scan pointer-events-none"
        style={{ height: '1px', background: COLORS.accent, opacity: 0.3 }}
      />

      {/* Corner brackets */}
      {[
        { top: 8, left: 8 },
        { top: 8, right: 8 },
        { bottom: 8, left: 8 },
        { bottom: 8, right: 8 },
      ].map((pos, i) => (
        <div key={i} className="absolute pointer-events-none" style={{ ...pos, opacity: 0.3 }}>
          <div style={{
            width: 10, height: 10,
            borderTop: i < 2 ? `2px solid ${COLORS.accent}` : 'none',
            borderBottom: i >= 2 ? `2px solid ${COLORS.accent}` : 'none',
            borderLeft: i % 2 === 0 ? `2px solid ${COLORS.accent}` : 'none',
            borderRight: i % 2 === 1 ? `2px solid ${COLORS.accent}` : 'none',
          }} />
        </div>
      ))}

      {/* Bounding boxes */}
      <svg className="absolute inset-0 w-full h-full pointer-events-none">
        {occupants.slice(0, 2).map((occ, i) => {
          const x = i === 0 ? '15%' : '55%'
          const y = i === 0 ? '30%' : '20%'
          const w = '30%'
          const h = '50%'
          const color = bboxColors[i] || bboxColors[2]
          return (
            <g key={occ.id}>
              <rect
                x={x} y={y} width={w} height={h}
                fill="none" stroke={color} strokeWidth="1"
                strokeDasharray="6 4" opacity="0.7"
              />
              <text
                x={x} y={parseInt(y) - 2 + '%'}
                fill={color} fontSize="8" fontFamily="'Courier New', monospace"
              >
                {occ.callsign}
              </text>
            </g>
          )
        })}
      </svg>

      {/* Labels */}
      <span className="absolute top-2 left-2 text-xs tracking-widest" style={{ fontSize: 9, color: COLORS.accent }}>
        CAM-01 // LIVE
      </span>

      <div className="absolute top-2 right-2 flex items-center gap-1">
        <span
          className="inline-block animate-pulse-dot"
          style={{ width: 5, height: 5, background: COLORS.accent }}
        />
        <span className="tracking-widest" style={{ fontSize: 9, color: COLORS.accent }}>
          REC
        </span>
      </div>

      <span className="absolute bottom-2 right-2" style={{ fontSize: 9, color: COLORS.textDeep }}>
        {fpsCurrent.toFixed(1)}fps // GPT-4o
      </span>

      <span className="absolute bottom-2 left-2" style={{ fontSize: 9, color: COLORS.textDeep }}>
        {ts}
      </span>
    </div>
  )
}

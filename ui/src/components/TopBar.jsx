import { useState, useEffect } from 'react'
import { COLORS } from '../constants/colors'

export default function TopBar({ isConnected }) {
  const [utc, setUtc] = useState('')

  useEffect(() => {
    const tick = () => {
      const d = new Date()
      setUtc(
        d.getUTCHours().toString().padStart(2, '0') + ':' +
        d.getUTCMinutes().toString().padStart(2, '0') + ':' +
        d.getUTCSeconds().toString().padStart(2, '0') + ' UTC'
      )
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])

  return (
    <div
      className="flex items-center justify-between px-4 py-2 font-mono"
      style={{
        background: COLORS.bg,
        borderBottom: `1px solid ${COLORS.borderFaint}`,
      }}
    >
      <div className="flex items-center gap-2">
        <span className="text-lg font-bold tracking-widest" style={{ color: COLORS.textPrimary }}>
          BREACHER
        </span>
        <span className="text-xs" style={{ color: COLORS.textDeep }}>
          // TACTICAL SCOUT SYSTEM v2.0
        </span>
      </div>

      <div className="flex items-center gap-4">
        {isConnected ? (
          <div className="flex items-center gap-1">
            <span
              className="inline-block w-2 h-2 animate-pulse-dot"
              style={{ background: COLORS.safe }}
            />
            <span className="text-xs uppercase tracking-widest" style={{ color: COLORS.safe }}>
              LIVE
            </span>
          </div>
        ) : (
          <span className="text-xs uppercase tracking-widest" style={{ color: COLORS.textMuted }}>
            OFFLINE
          </span>
        )}

        <span className="text-xs uppercase tracking-widest" style={{ color: COLORS.warning }}>
          MISSION: ACTIVE
        </span>

        <span className="text-xs" style={{ color: COLORS.textDim }}>
          {utc}
        </span>
      </div>
    </div>
  )
}

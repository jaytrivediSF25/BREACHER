import { COLORS } from '../constants/colors'

function Tile({ label, value, sub, valueColor, bar }) {
  return (
    <div className="px-3 py-2" style={{ background: COLORS.panelDeep, border: `1px solid ${COLORS.borderFaint}` }}>
      <div className="uppercase tracking-widest" style={{ fontSize: 9, color: COLORS.textDim }}>
        {label}
      </div>
      <div className="font-bold mt-1" style={{ fontSize: 22, color: valueColor || COLORS.textPrimary }}>
        {value}
      </div>
      <div style={{ fontSize: 10, color: COLORS.textDeep }}>
        {sub}
      </div>
      {bar && (
        <div className="mt-1" style={{ height: 3, background: COLORS.borderFaint }}>
          <div style={{ height: '100%', width: `${bar.pct}%`, background: bar.color, transition: 'width 0.5s ease' }} />
        </div>
      )}
    </div>
  )
}

export default function Metrics({ sceneState }) {
  const { latencyMs = 0, fpsCurrent = 0, batteryPct = 100, occupants = [] } = sceneState || {}

  const latencyColor = latencyMs < 150 ? COLORS.safe : latencyMs < 300 ? COLORS.warning : COLORS.accent
  const batteryColor = batteryPct > 30 ? COLORS.safe : batteryPct > 15 ? COLORS.warning : COLORS.accent

  return (
    <div style={{ background: COLORS.panel }}>
      <div className="px-3 pt-2 pb-1">
        <span className="uppercase tracking-widest" style={{ fontSize: 10, color: COLORS.textDim }}>
          SYSTEM
        </span>
      </div>

      <div className="grid grid-cols-2 gap-px p-1">
        <Tile label="SUBJECTS" value={occupants.length} sub="tracked" />
        <Tile
          label="TTS LATENCY"
          value={`${Math.round(latencyMs)}ms`}
          sub="smallest.ai"
          valueColor={latencyColor}
        />
        <Tile label="VISION" value={fpsCurrent.toFixed(1)} sub="frames/sec" />
        <Tile
          label="BATTERY"
          value={`${batteryPct}%`}
          sub=""
          bar={{ pct: batteryPct, color: batteryColor }}
        />
      </div>
    </div>
  )
}

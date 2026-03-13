import { COLORS } from '../constants/colors'

export default function RoomIntel({ room = {}, occupantCount = 0 }) {
  const rows = [
    { key: 'DIMENSIONS', value: room.dimensions || 'Unknown' },
    { key: 'OCCUPANTS', value: `${occupantCount} detected` },
    { key: 'DOORWAYS', value: `${room.doorways || 0} detected` },
    { key: 'WINDOWS', value: room.windows || 'Unknown' },
    { key: 'COVER', value: room.cover || 'None identified' },
    { key: 'LIGHTING', value: room.lighting || 'Normal' },
  ]

  return (
    <div style={{ background: COLORS.panel }}>
      <div className="px-3 pt-2 pb-1">
        <span className="uppercase tracking-widest" style={{ fontSize: 10, color: COLORS.textDim }}>
          ROOM INTELLIGENCE
        </span>
      </div>

      <div className="px-3 pb-2">
        {rows.map((row, i) => {
          const isLowLight = row.key === 'LIGHTING' &&
            (row.value.toLowerCase().includes('dim') || row.value.toLowerCase().includes('low'))
          return (
            <div
              key={i}
              className="flex justify-between py-1"
              style={{ borderBottom: `1px solid ${COLORS.borderDeep}` }}
            >
              <span className="uppercase tracking-widest" style={{ fontSize: 10, color: COLORS.textDim }}>
                {row.key}
              </span>
              <span style={{ fontSize: 11, color: isLowLight ? COLORS.warning : COLORS.textPrimary }}>
                {row.value}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

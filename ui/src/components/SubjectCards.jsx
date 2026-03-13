import { COLORS } from '../constants/colors'

const GREEK = { ALPHA: '\u03b1', BRAVO: '\u03b2', CHARLIE: '\u03b3', DELTA: '\u03b4', ECHO: '\u03b5' }

function Tag({ label, variant }) {
  const styles = {
    safe:   { color: COLORS.tagSafeText,   bg: COLORS.tagSafeBg,   border: COLORS.tagSafeBorder },
    warn:   { color: COLORS.tagWarnText,    bg: COLORS.tagWarnBg,   border: COLORS.tagWarnBorder },
    danger: { color: COLORS.tagDangerText,  bg: COLORS.tagDangerBg, border: COLORS.tagDangerBorder },
    gray:   { color: COLORS.tagGrayText,    bg: COLORS.tagGrayBg,   border: COLORS.tagGrayBorder },
  }
  const s = styles[variant] || styles.gray
  return (
    <span
      className="uppercase tracking-widest font-mono inline-block"
      style={{
        fontSize: 9,
        padding: '2px 6px',
        color: s.color,
        background: s.bg,
        border: `1px solid ${s.border}`,
      }}
    >
      {label}
    </span>
  )
}

function SubjectCard({ occupant }) {
  const tags = []
  if (occupant.weaponVisible)  tags.push({ label: 'WEAPON DETECTED', variant: 'danger' })
  if (occupant.moving)         tags.push({ label: 'MOVING', variant: 'danger' })
  if (occupant.facingEntry)    tags.push({ label: 'FACING ENTRY', variant: 'warn' })
  if (occupant.handsObscured)  tags.push({ label: 'HANDS OBSCURED', variant: 'warn' })
  if (occupant.handsVisible && !occupant.handsObscured)
    tags.push({ label: 'HANDS VISIBLE', variant: 'safe' })
  if (!occupant.weaponVisible) tags.push({ label: 'NO WEAPON', variant: 'safe' })
  tags.push({ label: occupant.posture, variant: 'gray' })

  return (
    <div className="px-3 py-2" style={{ borderBottom: `1px solid ${COLORS.borderFaint}` }}>
      <div className="flex items-baseline gap-2">
        <span style={{ fontSize: 10, color: COLORS.textDim }}>
          {GREEK[occupant.callsign] || '\u03b1'}
        </span>
        <span className="font-bold" style={{ fontSize: 14, color: COLORS.textPrimary }}>
          {occupant.callsign}
        </span>
      </div>
      <div className="mt-1" style={{ fontSize: 11, color: COLORS.textSecond, lineHeight: 1.4 }}>
        {occupant.position}
      </div>
      <div className="flex flex-wrap gap-1 mt-1">
        {tags.map((t, i) => <Tag key={i} label={t.label} variant={t.variant} />)}
      </div>
    </div>
  )
}

export default function SubjectCards({ occupants = [], threatLevel = 'LOW', threatPct = 0 }) {
  const threatColor = {
    LOW: COLORS.safe,
    MEDIUM: COLORS.warning,
    HIGH: COLORS.accent,
  }[threatLevel] || COLORS.safe

  return (
    <div style={{ background: COLORS.panel }}>
      <div className="px-3 pt-2 pb-1">
        <span className="uppercase tracking-widest" style={{ fontSize: 10, color: COLORS.textDim }}>
          DETECTED SUBJECTS
        </span>
      </div>

      {occupants.map(occ => <SubjectCard key={occ.id} occupant={occ} />)}

      {/* Threat level bar */}
      <div className="px-3 py-2">
        <div className="flex justify-between items-center">
          <span className="uppercase tracking-widest" style={{ fontSize: 10, color: COLORS.textDim }}>
            THREAT LEVEL
          </span>
          <span className="font-bold" style={{ fontSize: 11, color: threatColor }}>
            {threatLevel}
          </span>
        </div>
        <div className="mt-1" style={{ height: 3, background: COLORS.borderFaint }}>
          <div style={{ height: '100%', width: `${threatPct}%`, background: threatColor, transition: 'width 0.5s ease' }} />
        </div>
      </div>
    </div>
  )
}

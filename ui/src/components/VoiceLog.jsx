import { useRef, useEffect } from 'react'
import { COLORS } from '../constants/colors'

const COMMANDS = ['GO', 'HOLD', 'SWEEP', 'SITREP', 'ABORT']

export default function VoiceLog({ voiceLog = [], ttsActive = false, sendCommand }) {
  const scrollRef = useRef(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [voiceLog])

  const visibleLog = voiceLog.slice(-6)

  return (
    <div className="flex flex-col h-full" style={{ background: COLORS.panel }}>
      {/* Section label */}
      <div className="px-3 pt-2 pb-1">
        <span className="uppercase tracking-widest" style={{ fontSize: 10, color: COLORS.textDim }}>
          VOICE INTERFACE // SMALLEST.AI
        </span>
      </div>

      {/* TTS active bar */}
      {ttsActive && (
        <div className="flex items-center gap-2 px-3 py-1">
          <div className="flex items-end gap-px" style={{ height: 16 }}>
            {[0, 1, 2, 3, 4].map(i => (
              <div
                key={i}
                className={`animate-wave-${i}`}
                style={{
                  width: 3,
                  height: 8,
                  background: COLORS.accent,
                  transformOrigin: 'bottom',
                }}
              />
            ))}
          </div>
          <span className="uppercase tracking-widest" style={{ fontSize: 9, color: COLORS.accent }}>
            BROADCASTING
          </span>
        </div>
      )}

      {/* Transcript log */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-hidden px-3 py-1 flex flex-col gap-1"
      >
        {visibleLog.map((line, i) => {
          const isOp = line.speaker === 'OPERATOR'
          return (
            <div
              key={i}
              className="pl-2 py-1"
              style={{
                borderLeft: `2px solid ${isOp ? COLORS.info : COLORS.accent}`,
                background: isOp ? '#03060a' : '#0a0303',
              }}
            >
              <div className="uppercase tracking-widest" style={{ fontSize: 9, color: isOp ? COLORS.info : COLORS.accent }}>
                {line.speaker} <span style={{ color: COLORS.textDeep }}>{line.ts}</span>
              </div>
              <div style={{ fontSize: 11, lineHeight: 1.6, color: COLORS.textPrimary }}>
                {line.text}
              </div>
            </div>
          )
        })}
      </div>

      {/* Command buttons */}
      <div className="flex gap-2 px-3 py-2" style={{ borderTop: `1px solid ${COLORS.borderFaint}` }}>
        {COMMANDS.map(cmd => {
          const isAbort = cmd === 'ABORT'
          return (
            <button
              key={cmd}
              onClick={() => sendCommand && sendCommand(cmd.toLowerCase())}
              className="uppercase tracking-widest font-mono cursor-pointer transition-colors"
              style={{
                fontSize: 9,
                padding: '2px 8px',
                background: 'transparent',
                border: `1px solid ${isAbort ? COLORS.accent : COLORS.textGhost}`,
                color: isAbort ? COLORS.accent : COLORS.textMuted,
              }}
              onMouseEnter={e => {
                if (!isAbort) {
                  e.target.style.borderColor = COLORS.accent
                  e.target.style.color = COLORS.accent
                }
              }}
              onMouseLeave={e => {
                if (!isAbort) {
                  e.target.style.borderColor = COLORS.textGhost
                  e.target.style.color = COLORS.textMuted
                }
              }}
            >
              {cmd}
            </button>
          )
        })}
      </div>
    </div>
  )
}

import { useState, useEffect } from 'react'
import { COLORS } from '../constants/colors'

export default function MissionTimer() {
  const [seconds, setSeconds] = useState(0)

  useEffect(() => {
    const id = setInterval(() => setSeconds(s => s + 1), 1000)
    return () => clearInterval(id)
  }, [])

  const mm = String(Math.floor(seconds / 60)).padStart(2, '0')
  const ss = String(seconds % 60).padStart(2, '0')

  return (
    <div className="flex flex-col items-center justify-center" style={{ background: COLORS.panel }}>
      <div className="w-full px-3 pt-2 pb-1">
        <span className="uppercase tracking-widest" style={{ fontSize: 10, color: COLORS.textDim }}>
          ELAPSED
        </span>
      </div>
      <div className="font-bold font-mono" style={{ fontSize: 32, color: COLORS.textPrimary }}>
        {mm}:{ss}
      </div>
      <div className="uppercase tracking-widest mt-1 mb-2" style={{ fontSize: 9, color: COLORS.textDim }}>
        SINCE DEPLOYMENT
      </div>
    </div>
  )
}

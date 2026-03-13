import { useState, useCallback } from 'react'
import { COLORS } from './constants/colors'
import { MOCK_SCENE_STATE, MOCK_VOICE_LOG } from './constants/mockState'
import useWebSocket from './hooks/useWebSocket'
import TopBar from './components/TopBar'
import CameraFeed from './components/CameraFeed'
import VoiceLog from './components/VoiceLog'
import SubjectCards from './components/SubjectCards'
import RoomIntel from './components/RoomIntel'
import Metrics from './components/Metrics'
import TacticalMap from './components/TacticalMap'
import SweepProgress from './components/SweepProgress'
import MissionTimer from './components/MissionTimer'

export default function App() {
  const [sceneState, setSceneState] = useState(MOCK_SCENE_STATE)
  const [voiceLog, setVoiceLog] = useState(MOCK_VOICE_LOG)

  const onSceneState = useCallback((data) => {
    setSceneState(data)
  }, [])

  const onVoiceLine = useCallback((line) => {
    setVoiceLog(prev => [...prev, line])
  }, [])

  const { isConnected, sendCommand } = useWebSocket(onSceneState, onVoiceLine)

  return (
    <div className="h-screen w-screen flex flex-col font-mono" style={{ background: COLORS.bg }}>
      {/* Top bar */}
      <TopBar isConnected={isConnected} />

      {/* Three-column grid */}
      <div
        className="flex-1 grid min-h-0"
        style={{
          gridTemplateColumns: '30% 40% 30%',
        }}
      >
        {/* LEFT COLUMN: Camera + Voice Log */}
        <div
          className="flex flex-col min-h-0"
          style={{ borderRight: `1px solid ${COLORS.borderFaint}` }}
        >
          <div style={{ height: '45%' }}>
            <CameraFeed
              occupants={sceneState.occupants}
              fpsCurrent={sceneState.fpsCurrent}
            />
          </div>
          <div className="flex-1 min-h-0" style={{ borderTop: `1px solid ${COLORS.borderFaint}` }}>
            <VoiceLog
              voiceLog={voiceLog}
              ttsActive={sceneState.ttsActive}
              sendCommand={sendCommand}
            />
          </div>
        </div>

        {/* CENTER COLUMN: Subjects + Room Intel + Metrics */}
        <div
          className="flex flex-col min-h-0"
          style={{ borderRight: `1px solid ${COLORS.borderFaint}` }}
        >
          <div className="overflow-y-auto" style={{ height: '40%' }}>
            <SubjectCards
              occupants={sceneState.occupants}
              threatLevel={sceneState.threatLevel}
              threatPct={sceneState.threatPct}
            />
          </div>
          <div style={{ height: '30%', borderTop: `1px solid ${COLORS.borderFaint}` }}>
            <RoomIntel
              room={sceneState.room}
              occupantCount={sceneState.occupants?.length || 0}
            />
          </div>
          <div className="flex-1" style={{ borderTop: `1px solid ${COLORS.borderFaint}` }}>
            <Metrics sceneState={sceneState} />
          </div>
        </div>

        {/* RIGHT COLUMN: Map + Sweep + Timer */}
        <div className="flex flex-col min-h-0">
          <div style={{ height: '50%' }}>
            <TacticalMap sceneState={sceneState} />
          </div>
          <div style={{ height: '25%', borderTop: `1px solid ${COLORS.borderFaint}` }}>
            <SweepProgress
              sweepPct={sceneState.sweepPct}
              quadrants={sceneState.quadrants}
            />
          </div>
          <div className="flex-1" style={{ borderTop: `1px solid ${COLORS.borderFaint}` }}>
            <MissionTimer />
          </div>
        </div>
      </div>
    </div>
  )
}

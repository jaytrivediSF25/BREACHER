import { MOCK_SCENE_STATE, MOCK_VOICE_LOG } from '../constants/mockState'

export default function useMockData() {
  return {
    sceneState: MOCK_SCENE_STATE,
    voiceLog: MOCK_VOICE_LOG,
  }
}

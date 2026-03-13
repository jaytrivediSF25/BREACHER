import { useEffect, useRef, useState, useCallback } from 'react'

const WS_URL = 'ws://localhost:8765'
const RECONNECT_DELAY = 2000
const MAX_RECONNECT_DELAY = 16000

export default function useWebSocket(onSceneState, onVoiceLine) {
  const [isConnected, setIsConnected] = useState(false)
  const wsRef = useRef(null)
  const reconnectDelay = useRef(RECONNECT_DELAY)
  const reconnectTimer = useRef(null)

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      setIsConnected(true)
      reconnectDelay.current = RECONNECT_DELAY
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.sceneState && onSceneState) {
          onSceneState(data.sceneState)
        }
        if (data.voiceLine && onVoiceLine) {
          onVoiceLine(data.voiceLine)
        }
      } catch (e) {
        // ignore parse errors
      }
    }

    ws.onclose = () => {
      setIsConnected(false)
      reconnectTimer.current = setTimeout(() => {
        reconnectDelay.current = Math.min(
          reconnectDelay.current * 2,
          MAX_RECONNECT_DELAY
        )
        connect()
      }, reconnectDelay.current)
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [onSceneState, onVoiceLine])

  const sendCommand = useCallback((command) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ command }))
    }
  }, [])

  useEffect(() => {
    connect()
    return () => {
      clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [connect])

  return { isConnected, sendCommand }
}

import { useState, useCallback } from 'react'
import LobbyScreen from './components/LobbyScreen.jsx'
import GameScreen from './components/GameScreen.jsx'
import PassAndPlayGameScreen from './components/PassAndPlayGameScreen.jsx'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function App() {
  const [session, setSession] = useState(null)
  // session: { roomId, playerId, playMode, humanRole? }

  const handleCreateRoom = useCallback(async (playerName, scenarioId, playMode, humanRole, evalMode) => {
    const res = await fetch(`${API_BASE}/api/rooms`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scenario_id: scenarioId || null,
        play_mode: playMode || 'MULTIPLAYER',
        human_role: humanRole || 'ATTACKER',
        eval_mode: evalMode || 'EXACT',
      }),
    })
    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.detail || 'Failed to create room')
    }
    const data = await res.json()

    if (playMode === 'PASS_AND_PLAY') {
      // No player name needed — P1/P2 are assigned automatically by PassAndPlayGameScreen
      setSession({ roomId: data.room_id, playMode: 'PASS_AND_PLAY' })
    } else {
      const base = playerName?.trim() || 'Player'
      const playerId = `${base}_${Math.random().toString(36).slice(2, 6)}`
      setSession({ roomId: data.room_id, playerId, displayName: base, playMode: data.play_mode })
    }
  }, [])

  const handleJoinRoom = useCallback((roomId, playerName) => {
    const base = playerName?.trim() || 'Player'
    const playerId = `${base}_${Math.random().toString(36).slice(2, 6)}`
    setSession({ roomId: roomId.trim().toUpperCase(), playerId, displayName: base, playMode: 'MULTIPLAYER' })
  }, [])

  const handleLeave = useCallback(() => setSession(null), [])

  if (!session) {
    return <LobbyScreen onCreateRoom={handleCreateRoom} onJoinRoom={handleJoinRoom} />
  }

  if (session.playMode === 'PASS_AND_PLAY') {
    return <PassAndPlayGameScreen roomId={session.roomId} onLeave={handleLeave} />
  }

  return (
    <GameScreen
      roomId={session.roomId}
      playerId={session.playerId}
      displayName={session.displayName}
      onLeave={handleLeave}
    />
  )
}

import { useState, useEffect, useRef, useCallback } from 'react'

const WS_BASE = import.meta.env.VITE_WS_URL || `ws://${window.location.hostname}:8000`

export function useGameSocket(roomId, playerId, displayName) {
  const [connected, setConnected] = useState(false)
  const [gameState, setGameState] = useState(null)
  const [error, setError] = useState(null)
  const [submitted, setSubmitted] = useState(false)

  // Live evaluation turns: [{turn, total_turns, user_msg, response, forbidden_found}]
  const [evalTurns, setEvalTurns] = useState([])
  const [pendingTurn, setPendingTurn] = useState(null) // turn currently "thinking"
  const [aiThinking, setAiThinking] = useState(false)  // AI opponent generating
  const [streamingText, setStreamingText] = useState('') // tokens as they arrive

  const wsRef = useRef(null)

  const connect = useCallback(() => {
    if (!roomId || !playerId) return
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const dn = (displayName || playerId).trim()
    const url = `${WS_BASE}/ws/${roomId}/${playerId}?display_name=${encodeURIComponent(dn)}`
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => { setConnected(true); setError(null) }
    ws.onmessage = (e) => {
      try { handleMessage(JSON.parse(e.data)) }
      catch (err) { console.error('[WS] parse error', err) }
    }
    ws.onclose = () => setConnected(false)
    ws.onerror = () => setError('WebSocket connection error')
  }, [roomId, playerId, displayName])

  const handleMessage = useCallback((msg) => {
    switch (msg.type) {
      case 'state':
      case 'phase_change':
        if (msg.room) {
          setGameState(msg.room)
          // Reset eval + submitted state when entering a new phase
          if (msg.room.phase !== 'EVALUATING') {
            setEvalTurns([])
            setPendingTurn(null)
            setAiThinking(false)
            setStreamingText('')
          }
          // Reset submitted flag whenever we land back in LOBBY or DRAFTING
          // so play-again role-swaps don't leave the new defender stuck on a
          // "waiting for opponent" screen.
          if (msg.room.phase === 'LOBBY' || msg.room.phase === 'DRAFTING') {
            setSubmitted(false)
          }
        }
        break

      case 'tick':
        setGameState((prev) => prev ? { ...prev, time_remaining: msg.time_remaining } : prev)
        break

      case 'submitted':
        setSubmitted(true)
        break

      // ── Streaming evaluation ───────────────────────────────────────────
      case 'turn_start':
        setStreamingText('')  // clear any previous streaming text
        setPendingTurn({
          turn: msg.turn,
          total_turns: msg.total_turns,
          user_msg: msg.user_msg,
        })
        break

      case 'stream_chunk':
        setStreamingText((prev) => prev + msg.text)
        break

      case 'stream_complete':
        setStreamingText('')  // clear; turn_result will follow
        break

      case 'turn_result':
        setPendingTurn(null)
        setStreamingText('')
        setEvalTurns((prev) => [
          ...prev,
          {
            turn: msg.turn,
            total_turns: msg.total_turns,
            user_msg: msg.user_msg || '',
            response: msg.response,
            forbidden_found: msg.forbidden_found,
            forbidden_phrase: msg.forbidden_phrase,
            turn_attacker_won: msg.turn_attacker_won,
            context_reset: msg.context_reset,
            prompts_succeeded: msg.prompts_succeeded,
          },
        ])
        break

      // ── AI opponent ────────────────────────────────────────────────────
      case 'ai_thinking':
        setAiThinking(true)
        break

      case 'player_left':
        setError(msg.message || 'Opponent disconnected')
        break

      case 'error':
        setError(msg.message)
        break

      default:
        console.log('[WS] unknown:', msg.type, msg)
    }
  }, [])

  useEffect(() => {
    connect()
    return () => wsRef.current?.close()
  }, [connect])

  // Keep turn user_msg in sync: turn_result doesn't carry user_msg so we track it
  // via pendingTurn → evalTurns merge
  useEffect(() => {
    if (!pendingTurn) return
    // nothing — pendingTurn is the "thinking" indicator displayed in EvaluatingScreen
  }, [pendingTurn])

  const send = useCallback((data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN)
      wsRef.current.send(JSON.stringify(data))
  }, [])

  const sendReady = useCallback(() => send({ type: 'ready' }), [send])
  const submitDefender = useCallback((p) => send({ type: 'submit_defender', system_prompt: p }), [send])
  const submitAttacker = useCallback((p) => send({ type: 'submit_attacker', prompts: p }), [send])
  const playAgain = useCallback(() => { setSubmitted(false); setError(null); setEvalTurns([]); setStreamingText(''); send({ type: 'play_again' }) }, [send])
  const sendPassAndPlayDone = useCallback(() => send({ type: 'pass_and_play_done' }), [send])

  return {
    connected, gameState, error, submitted,
    evalTurns, pendingTurn, aiThinking, streamingText,
    sendReady, submitDefender, submitAttacker, playAgain, sendPassAndPlayDone,
  }
}

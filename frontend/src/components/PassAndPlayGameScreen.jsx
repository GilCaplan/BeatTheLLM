/**
 * PassAndPlayGameScreen
 *
 * Opens TWO WebSocket connections (Player_1 + Player_2) from the same browser
 * window. Shows the active player's view based on pass_and_play_turn, with a
 * lock screen between turns so players can't see each other's inputs.
 */
import { useState } from 'react'
import { useGameSocket } from '../hooks/useGameSocket.js'
import StatusBar from './StatusBar.jsx'
import WaitingLobby from './WaitingLobby.jsx'
import DraftingScreen from './DraftingScreen.jsx'
import EvaluatingScreen from './EvaluatingScreen.jsx'
import ResultsScreen from './ResultsScreen.jsx'

const P1 = 'Player_1'
const P2 = 'Player_2'

export default function PassAndPlayGameScreen({ roomId, onLeave }) {
  // Both players' sockets — always open from this single window
  const p1 = useGameSocket(roomId, P1)
  const p2 = useGameSocket(roomId, P2)

  // Lock screen between turns
  const [handedOver, setHandedOver] = useState(false)

  // Use either socket's game state (they're in sync after the first state message)
  const gameState = p1.gameState || p2.gameState
  const phase = gameState?.phase || 'LOBBY'
  const turn = gameState?.pass_and_play_turn  // null in LOBBY/EVALUATING/RESULTS

  // Who's up right now?
  const activePlayerId = turn || P1
  const activeSock = activePlayerId === P2 ? p2 : p1
  const activeRole = gameState?.players?.[activePlayerId]?.role

  const connected = p1.connected && p2.connected
  const evalTurns = p1.evalTurns.length ? p1.evalTurns : p2.evalTurns
  const pendingTurn = p1.pendingTurn || p2.pendingTurn
  const streamingText = p1.streamingText || p2.streamingText
  const totalTurns = evalTurns.length > 0
    ? evalTurns[0].total_turns
    : (pendingTurn?.total_turns || null)

  // ── Ready: both players ready themselves ──────────────────────────────────
  const handleReady = () => {
    if (!p1.gameState?.players?.[P1]?.ready) p1.sendReady()
    if (!p2.gameState?.players?.[P2]?.ready) p2.sendReady()
  }

  // ── Drafting submit ────────────────────────────────────────────────────────
  const handleSubmitDefender = (prompt) => {
    if (activeRole === 'DEFENDER') activeSock.submitDefender(prompt)
  }
  const handleSubmitAttacker = (prompts) => {
    if (activeRole === 'ATTACKER') activeSock.submitAttacker(prompts)
  }

  // After submitting, show the lock screen so the other player can't see
  const handlePassAndPlayDone = () => {
    activeSock.sendPassAndPlayDone()
    setHandedOver(true)
  }

  // When the lock screen "I'M READY" is pressed, reveal the new player's view
  const handleUnlock = () => {
    setHandedOver(false)
  }

  // ── Play Again ─────────────────────────────────────────────────────────────
  const handlePlayAgain = () => {
    p1.playAgain()
    setHandedOver(false)
  }

  if (!connected && !gameState) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="terminal-box text-center p-8">
          <div className="text-2xl mb-4 animate-pulse">Initializing...</div>
          <div className="text-green-700 text-sm">Opening both player connections</div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex flex-col">
      <StatusBar
        roomId={roomId}
        playerId={activePlayerId}
        phase={phase}
        role={activeRole}
        timeRemaining={gameState?.time_remaining}
        playerCount={Object.keys(gameState?.players || {}).length}
        connected={connected}
        playMode="PASS_AND_PLAY"
        onLeave={onLeave}
      />

      <main className="flex-1 p-4">
        {/* Lock screen between turns during DRAFTING */}
        {phase === 'DRAFTING' && handedOver && (
          <LockScreen activeRole={activeRole} onUnlock={handleUnlock} />
        )}

        {/* Normal views */}
        {!handedOver && (
          <>
            {phase === 'LOBBY' && (
              <WaitingLobby
                roomId={roomId}
                gameState={gameState}
                playerId={activePlayerId}
                onReady={handleReady}
                onLeave={onLeave}
                isPassAndPlay
              />
            )}

            {phase === 'DRAFTING' && (
              <DraftingScreen
                gameState={{ ...gameState, your_role: activeRole }}
                playerId={activePlayerId}
                submitted={activeSock.submitted}
                isPassAndPlay
                onSubmitDefender={handleSubmitDefender}
                onSubmitAttacker={handleSubmitAttacker}
                onPassAndPlayDone={handlePassAndPlayDone}
              />
            )}

            {phase === 'EVALUATING' && (
              <EvaluatingScreen
                evalTurns={evalTurns}
                pendingTurn={pendingTurn}
                totalTurns={totalTurns}
                streamingText={streamingText}
              />
            )}

            {phase === 'RESULTS' && (
              <ResultsScreen
                gameState={gameState}
                playerId={activePlayerId}
                onPlayAgain={handlePlayAgain}
                onLeave={onLeave}
              />
            )}
          </>
        )}
      </main>
    </div>
  )
}

function LockScreen({ activeRole, onUnlock }) {
  const nextRole = activeRole === 'DEFENDER' ? 'ATTACKER' : 'DEFENDER'
  const nextLabel = nextRole === 'ATTACKER' ? '⚔ ATTACKER' : '🛡 DEFENDER'
  const nextColor = nextRole === 'ATTACKER' ? 'text-hacker-red' : 'text-blue-400'
  const borderColor = nextRole === 'ATTACKER' ? 'border-hacker-red' : 'border-blue-500'

  return (
    <div className="min-h-[70vh] flex items-center justify-center">
      <div className={`terminal-box text-center p-12 max-w-md ${borderColor}`}>
        <div className="text-5xl mb-4">🔒</div>
        <div className="text-green-700 text-xs tracking-widest uppercase mb-4">
          Pass &amp; Play — Screen Locked
        </div>
        <div className={`text-3xl font-bold mb-4 ${nextColor}`}>
          {nextLabel}'s Turn
        </div>
        <p className="text-sm text-green-700 mb-8">
          Hand the device to the{' '}
          <span className={`font-bold ${nextColor}`}>{nextRole}</span>.{' '}
          <br />Press the button when ready to view your secret prompt.
        </p>
        <button
          onClick={onUnlock}
          className={nextRole === 'ATTACKER' ? 'btn-danger px-10 py-3 text-lg' : 'btn-primary px-10 py-3 text-lg'}
        >
          I'M READY — SHOW MY SCREEN
        </button>
        <div className="mt-4 text-green-900 text-xs">
          # Do not look while the other player is reading!
        </div>
      </div>
    </div>
  )
}

import { useGameSocket } from '../hooks/useGameSocket.js'
import WaitingLobby from './WaitingLobby.jsx'
import DraftingScreen from './DraftingScreen.jsx'
import EvaluatingScreen from './EvaluatingScreen.jsx'
import ResultsScreen from './ResultsScreen.jsx'
import StatusBar from './StatusBar.jsx'
import PassAndPlayGate from './PassAndPlayGate.jsx'

export default function GameScreen({ roomId, playerId, onLeave }) {
  const {
    connected,
    gameState,
    error,
    submitted,
    evalTurns,
    pendingTurn,
    sendReady,
    submitDefender,
    submitAttacker,
    playAgain,
    sendPassAndPlayDone,
  } = useGameSocket(roomId, playerId)

  const phase = gameState?.phase || 'LOBBY'
  const playerCount = Object.keys(gameState?.players || {}).length
  const playMode = gameState?.play_mode || 'MULTIPLAYER'
  const passAndPlayTurn = gameState?.pass_and_play_turn

  // Pass-and-play: show a "hand off screen" when it's not this player's turn during DRAFTING
  const isPassAndPlay = playMode === 'PASS_AND_PLAY'
  const isMyTurn = !isPassAndPlay || passAndPlayTurn === null || passAndPlayTurn === playerId

  if (!connected && !gameState) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="terminal-box text-center p-8">
          <div className="text-2xl mb-4 animate-pulse">Connecting...</div>
          <div className="text-green-700 text-sm">Establishing secure channel to room {roomId}</div>
          {error && <div className="text-hacker-red mt-4">[ERROR] {error}</div>}
        </div>
      </div>
    )
  }

  if (error && phase === 'LOBBY' && !gameState) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="terminal-box text-center p-8 border-hacker-red">
          <div className="text-hacker-red text-2xl mb-4">[CONNECTION LOST]</div>
          <div className="text-sm mb-6">{error}</div>
          <button onClick={onLeave} className="btn-danger">RETURN TO BASE</button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex flex-col">
      <StatusBar
        roomId={roomId}
        playerId={playerId}
        phase={phase}
        role={gameState?.your_role}
        timeRemaining={gameState?.time_remaining}
        playerCount={playerCount}
        connected={connected}
        playMode={playMode}
        onLeave={onLeave}
      />

      <main className="flex-1 p-4">
        {/* Pass-and-play handoff gate during drafting */}
        {isPassAndPlay && phase === 'DRAFTING' && !isMyTurn && (
          <PassAndPlayGate
            waitingForRole={gameState?.players?.[passAndPlayTurn]?.role || 'OTHER'}
            onReady={sendPassAndPlayDone}
          />
        )}

        {/* Normal rendering when it's this player's turn (or not pass-and-play) */}
        {(phase !== 'DRAFTING' || !isPassAndPlay || isMyTurn) && (
          <>
            {phase === 'LOBBY' && (
              <WaitingLobby
                roomId={roomId}
                gameState={gameState}
                playerId={playerId}
                onReady={sendReady}
                onLeave={onLeave}
                isPassAndPlay={isPassAndPlay}
              />
            )}

            {phase === 'DRAFTING' && (
              <DraftingScreen
                gameState={gameState}
                playerId={playerId}
                submitted={submitted}
                isPassAndPlay={isPassAndPlay}
                onSubmitDefender={submitDefender}
                onSubmitAttacker={submitAttacker}
                onPassAndPlayDone={sendPassAndPlayDone}
              />
            )}

            {phase === 'EVALUATING' && (
              <EvaluatingScreen
                evalTurns={evalTurns}
                pendingTurn={pendingTurn}
                totalTurns={
                  pendingTurn?.total_turns ||
                  evalTurns[evalTurns.length - 1]?.total_turns
                }
              />
            )}

            {phase === 'RESULTS' && (
              <ResultsScreen
                gameState={gameState}
                playerId={playerId}
                onPlayAgain={playAgain}
                onLeave={onLeave}
              />
            )}
          </>
        )}
      </main>
    </div>
  )
}

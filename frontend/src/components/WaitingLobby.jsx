export default function WaitingLobby({ roomId, gameState, playerId, onReady, onLeave, isPassAndPlay }) {
  const players = gameState?.players || {}
  const playerCount = Object.keys(players).length
  const myReady = players[playerId]?.ready || false
  const myRole = gameState?.your_role || players[playerId]?.role
  const scenario = gameState?.scenario

  const copyCode = () => navigator.clipboard.writeText(roomId)

  return (
    <div className="max-w-2xl mx-auto mt-8 space-y-6">
      {/* Header */}
      <div className="terminal-box text-center">
        <div className="text-green-700 text-sm mb-2">SECURE CHANNEL ESTABLISHED</div>
        <div className="text-4xl font-bold glow-text mb-1">{roomId}</div>
        <div className="text-green-700 text-sm mb-4">Share this code with your opponent</div>
        <button onClick={copyCode} className="btn-primary text-xs py-1 px-4">
          COPY CODE
        </button>
      </div>

      {/* Role Assignment */}
      {myRole && (
        <div className={`terminal-box text-center ${myRole === 'DEFENDER' ? 'border-blue-500' : 'border-hacker-red'
          }`}>
          <div className="text-xs text-green-700 mb-2 tracking-widest">YOUR ROLE</div>
          <div className={`text-3xl font-bold mb-3 ${myRole === 'DEFENDER' ? 'role-defender' : 'role-attacker'
            }`}>
            {myRole === 'DEFENDER' ? '🛡 DEFENDER' : '⚔ ATTACKER'}
          </div>
          {myRole === 'DEFENDER' ? (
            <p className="text-sm text-green-700 max-w-md mx-auto">
              You will craft a <span className="text-blue-400">System Prompt</span> to
              prevent the AI from saying the forbidden phrase.
            </p>
          ) : (
            <p className="text-sm text-green-700 max-w-md mx-auto">
              You will craft <span className="text-hacker-red">attack prompts</span> to
              trick the AI into saying the forbidden phrase.
            </p>
          )}
        </div>
      )}

      {/* Scenario Preview — role-gated:
           DEFENDER sees full system_setting (needed to craft their defense)
           ATTACKER only sees title + forbidden phrase + hint (no AI persona leak) */}
      {scenario && (
        <div className={`terminal-box ${myRole === 'DEFENDER' ? 'border-blue-900' : 'border-green-900'}`}>
          <div className="text-xs text-green-700 mb-3 tracking-widest uppercase">
            &gt; Mission Brief
          </div>

          {myRole === 'DEFENDER' ? (
            /* Defender: full scenario context so they know what to protect */
            <>
              <div className="text-xs text-blue-400 mb-1 tracking-widest uppercase">AI Persona (you are protecting):</div>
              <p className="text-sm mb-3 text-blue-300 italic">{scenario.system_setting || scenario.description}</p>
            </>
          ) : (
            /* Attacker: only the theme name — not the actual system prompt */
            <>
              <div className="text-xs text-green-700 mb-1 tracking-widest uppercase">Scenario:</div>
              <p className="text-sm mb-3 text-hacker-green font-bold">{scenario.title}</p>
            </>
          )}

          <div className="border-t border-green-900 pt-3">
            <span className="text-xs text-green-700 uppercase tracking-widest">Target phrase: </span>
            <span className="text-hacker-red font-bold">"{scenario.forbidden_phrase}"</span>
          </div>
          {scenario.hint && (
            <div className="mt-2 text-xs text-green-800">
              # {scenario.hint}
            </div>
          )}
        </div>
      )}

      {/* Player Status */}
      <div className="terminal-box">
        <div className="text-xs text-green-700 mb-3 tracking-widest uppercase">
          &gt; Connection Status ({playerCount}/2)
        </div>
        <div className="space-y-2">
          {Object.entries(players).map(([pid, info]) => (
            <div key={pid} className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${info.ready ? 'bg-hacker-green' : 'bg-yellow-600'}`} />
                <span className={pid === playerId ? 'text-hacker-green' : 'text-green-600'}>
                  {info.display_name ?? pid}{pid === playerId ? ' (you)' : ''}
                </span>
              </div>
              <div className="flex items-center gap-3">
                <span className={`text-xs ${info.role === 'DEFENDER' ? 'role-defender' : 'role-attacker'
                  }`}>
                  [{info.role || 'UNASSIGNED'}]
                </span>
                <span className={`text-xs ${info.ready ? 'text-hacker-green' : 'text-yellow-600'}`}>
                  {info.ready ? '● READY' : '○ WAITING'}
                </span>
              </div>
            </div>
          ))}
          {playerCount < 2 && (
            <div className="flex items-center gap-2 text-sm text-green-900">
              <span className="w-2 h-2 rounded-full bg-gray-800 animate-pulse" />
              <span>Waiting for opponent...</span>
            </div>
          )}
        </div>
      </div>

      {/* Ready Button */}
      {playerCount === 2 && (
        <div className="text-center">
          {myReady ? (
            <div className="text-hacker-green font-bold text-lg animate-pulse">
              ● READY — Waiting for opponent...
            </div>
          ) : (
            <button onClick={onReady} className="btn-primary text-lg px-12 py-3">
              &gt; I'M READY
            </button>
          )}
        </div>
      )}

      {/* Leave Room */}
      <div className="text-center pb-4">
        <button
          onClick={onLeave}
          className="text-green-900 hover:text-hacker-red text-xs tracking-widest transition-colors border border-green-900 hover:border-hacker-red px-4 py-2"
        >
          ✕ LEAVE ROOM
        </button>
      </div>
    </div>
  )
}

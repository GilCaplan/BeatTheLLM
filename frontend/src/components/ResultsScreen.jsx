import { useState } from 'react'

export default function ResultsScreen({ gameState, playerId, onPlayAgain, onLeave }) {
  const result = gameState?.result
  const scenario = gameState?.scenario || {}
  const players = gameState?.players || {}
  const [showSystemPrompt, setShowSystemPrompt] = useState(false)

  if (!result) {
    return (
      <div className="max-w-2xl mx-auto mt-16 terminal-box text-center">
        <div className="animate-pulse">Loading results...</div>
      </div>
    )
  }

  const {
    attacker_won, llm_output, forbidden_phrase, chat_log,
    scenario_setting, defender_prompt, full_system_prompt,
    winner_id, loser_id,
  } = result

  const iWon = winner_id === playerId
  const myRole = gameState?.your_role || players[playerId]?.role

  const verdictText = attacker_won ? '⚔ JAILBREAK SUCCESSFUL' : '🛡 DEFENSE HELD'
  const verdictColor = attacker_won ? 'text-hacker-red' : 'text-blue-400'
  const verdictBorder = attacker_won ? 'border-hacker-red' : 'border-blue-500'

  return (
    <div className="max-w-4xl mx-auto mt-4 space-y-4">

      {/* Main Verdict */}
      <div className={`terminal-box text-center ${verdictBorder}`}>
        <div className="text-xs text-green-700 mb-2 tracking-widest uppercase">// VERDICT</div>
        <div
          className={`text-4xl font-bold mb-3 ${verdictColor}`}
          style={{ textShadow: attacker_won ? '0 0 20px #e94560' : '0 0 20px #60a5fa' }}
        >
          {verdictText}
        </div>
        <div className={`text-xl font-bold mb-2 ${iWon ? 'text-hacker-green' : 'text-hacker-red'}`}>
          {iWon ? '● YOU WIN' : '○ YOU LOSE'}
        </div>
        <div className="text-sm text-green-700">
          {attacker_won
            ? `The AI said "${forbidden_phrase}" — the Attacker wins!`
            : `The AI avoided "${forbidden_phrase}" — the Defender wins!`}
        </div>
      </div>

      {/* System Prompt used (collapsible) */}
      <div className="terminal-box">
        <button
          onClick={() => setShowSystemPrompt((v) => !v)}
          className="w-full text-left flex items-center justify-between"
        >
          <span className="text-xs text-green-700 tracking-widest uppercase">
            // System Prompt Sent to LLM
          </span>
          <span className="text-green-700 text-xs">{showSystemPrompt ? '▲ collapse' : '▼ expand'}</span>
        </button>

        {showSystemPrompt && (
          <div className="mt-3 space-y-3">
            {/* Scenario base */}
            <div className="border border-blue-900 p-3 text-sm">
              <div className="text-xs text-blue-400 mb-2 tracking-widest uppercase">
                Scenario Base (always active)
              </div>
              <pre className="text-blue-300 whitespace-pre-wrap text-xs leading-relaxed">
                {scenario_setting || scenario.system_setting || '—'}
              </pre>
            </div>

            {/* Defender additions */}
            <div className={`border p-3 text-sm ${defender_prompt ? 'border-green-800' : 'border-gray-800'}`}>
              <div className="text-xs text-green-700 mb-2 tracking-widest uppercase">
                Defender's Additions
              </div>
              <pre className="text-green-400 whitespace-pre-wrap text-xs leading-relaxed">
                {defender_prompt || <span className="text-green-900 italic">(none — only scenario base was used)</span>}
              </pre>
            </div>
          </div>
        )}
      </div>

      {/* Forbidden Phrase Detection */}
      <div className="terminal-box">
        <div className="text-xs text-green-700 mb-2 tracking-widest uppercase">
          // Forbidden Phrase Detection
        </div>
        <div className="flex items-center gap-3">
          <span className={`text-xl font-bold ${attacker_won ? 'text-hacker-red' : 'text-hacker-green'}`}>
            {attacker_won ? '✓ DETECTED' : '✗ NOT DETECTED'}
          </span>
          <span className="text-green-700 text-sm">
            phrase: <span className={attacker_won ? 'text-hacker-red font-bold' : 'text-hacker-green font-bold'}>
              "{forbidden_phrase}"
            </span>
          </span>
        </div>
      </div>

      {/* Full Chat Log */}
      <div className="terminal-box">
        <div className="text-xs text-green-700 mb-4 tracking-widest uppercase">
          // Full Chat Transcript
        </div>
        <div className="space-y-3">
          {(chat_log || []).map((msg, i) => (
            <div
              key={i}
              className={`p-3 text-sm ${
                msg.role === 'user'
                  ? 'border-l-2 border-hacker-red bg-red-950 bg-opacity-20'
                  : 'border-l-2 border-hacker-green bg-green-950 bg-opacity-20'
              }`}
            >
              <div className={`text-xs font-bold mb-1 tracking-widest ${
                msg.role === 'user' ? 'text-hacker-red' : 'text-hacker-green'
              }`}>
                {msg.role === 'user' ? '[ATTACKER]' : '[AI RESPONSE]'}
              </div>
              <div className={`${msg.role === 'user' ? 'text-red-300' : 'text-green-300'} whitespace-pre-wrap`}>
                {highlightForbidden(msg.content, forbidden_phrase)}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-4 justify-center pb-8">
        <button onClick={onPlayAgain} className="btn-primary">
          PLAY AGAIN (SWAP ROLES)
        </button>
        <button onClick={onLeave} className="btn-danger">
          RETURN TO LOBBY
        </button>
      </div>
    </div>
  )
}

function highlightForbidden(text, phrase) {
  if (!text || !phrase) return text
  const regex = new RegExp(`(${escapeRegex(phrase)})`, 'gi')
  const parts = text.split(regex)
  return parts.map((part, i) =>
    regex.test(part)
      ? <mark key={i} style={{ background: '#e94560', color: '#000', padding: '0 2px', borderRadius: 2 }}>{part}</mark>
      : part
  )
}

function escapeRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

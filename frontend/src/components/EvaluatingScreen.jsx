import { useEffect, useRef } from 'react'

/**
 * EvaluatingScreen — live turn-by-turn chat playback.
 * Each attacker prompt appears, then the AI "thinks", then the response appears.
 */
export default function EvaluatingScreen({ evalTurns = [], pendingTurn, totalTurns, streamingText = '' }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [evalTurns, pendingTurn, streamingText])

  const allDone = !pendingTurn && evalTurns.length > 0 && evalTurns.length === (totalTurns || evalTurns.length)

  return (
    <div className="max-w-3xl mx-auto mt-4 space-y-4">
      {/* Header */}
      <div className="terminal-box text-center py-4">
        <div className={`text-xl font-bold mb-1 ${allDone ? 'text-hacker-green' : 'text-hacker-yellow animate-pulse'}`}>
          {allDone ? '● EVALUATION COMPLETE' : '⚡ RUNNING INFERENCE...'}
        </div>
        <div className="text-xs text-green-700">
          {evalTurns.length} / {totalTurns || '?'} turns processed
        </div>
      </div>

      {/* Turn-by-turn chat */}
      <div className="terminal-box space-y-4">
        <div className="text-xs text-green-700 mb-2 tracking-widest uppercase">
          // Live Chat Transcript
        </div>

        {evalTurns.map((t) => (
          <TurnBlock key={t.turn} turn={t} />
        ))}

        {/* Pending turn — showing attacker prompt, AI streaming */}
        {pendingTurn && (
          <PendingTurnBlock turn={pendingTurn} streamingText={streamingText} />
        )}

        {/* Empty state */}
        {evalTurns.length === 0 && !pendingTurn && (
          <div className="text-green-800 text-sm animate-pulse">
            Initializing inference engine...
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {allDone && (
        <div className="terminal-box text-center py-3">
          <div className="text-hacker-green text-sm animate-pulse">
            Computing winner... standby...
          </div>
        </div>
      )}
    </div>
  )
}

function TurnBlock({ turn }) {
  const phraseFound = turn.forbidden_found

  return (
    <div className="space-y-2">
      {/* Turn label */}
      <div className="text-xs text-green-800 tracking-widest">
        — TURN {turn.turn} —
      </div>

      {/* Attacker message */}
      <div className="border-l-2 border-hacker-red bg-red-950 bg-opacity-20 p-3">
        <div className="text-xs font-bold text-hacker-red mb-1 tracking-widest">[ATTACKER]</div>
        <div className="text-red-300 text-sm">{turn.user_msg}</div>
      </div>

      {/* AI response */}
      <div className={`border-l-2 p-3 ${phraseFound ? 'border-hacker-red bg-red-950 bg-opacity-30' : 'border-hacker-green bg-green-950 bg-opacity-20'}`}>
        <div className={`text-xs font-bold mb-1 tracking-widest ${phraseFound ? 'text-hacker-red' : 'text-hacker-green'}`}>
          [AI RESPONSE]{phraseFound ? ' ⚠ FORBIDDEN PHRASE DETECTED' : ''}
        </div>
        <div className={`text-sm ${phraseFound ? 'text-red-300' : 'text-green-300'}`}>
          {highlightForbidden(turn.response, turn.forbidden_phrase)}
        </div>
      </div>
    </div>
  )
}

function PendingTurnBlock({ turn, streamingText = '' }) {
  return (
    <div className="space-y-2 opacity-80">
      <div className="text-xs text-green-800 tracking-widest">
        — TURN {turn.turn} —
      </div>

      {/* Attacker message */}
      <div className="border-l-2 border-hacker-red bg-red-950 bg-opacity-20 p-3">
        <div className="text-xs font-bold text-hacker-red mb-1 tracking-widest">[ATTACKER]</div>
        <div className="text-red-300 text-sm">{turn.user_msg}</div>
      </div>

      {/* AI response area — streaming typewriter or dots */}
      <div className="border-l-2 border-hacker-yellow bg-yellow-950 bg-opacity-10 p-3">
        <div className="text-xs font-bold text-hacker-yellow mb-2 tracking-widest">[AI RESPONSE]</div>
        {streamingText ? (
          <div className="text-sm text-yellow-200 whitespace-pre-wrap">
            {streamingText}
            <span className="inline-block w-1.5 h-4 bg-hacker-yellow ml-0.5 animate-pulse align-middle" />
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <ThinkingDots />
            <span className="text-hacker-yellow text-xs">Model processing...</span>
          </div>
        )}
      </div>
    </div>
  )
}

function ThinkingDots() {
  return (
    <div className="flex gap-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-2 h-2 rounded-full bg-hacker-yellow animate-pulse"
          style={{ animationDelay: `${i * 0.2}s` }}
        />
      ))}
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

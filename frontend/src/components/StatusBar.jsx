export default function StatusBar({
  roomId, playerId, phase, role, timeRemaining, playerCount, connected, playMode, onLeave, onShowRules
}) {
  const formatTime = (s) => {
    if (s == null) return '--:--'
    const m = Math.floor(s / 60)
    const sec = s % 60
    return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
  }

  const phaseColors = {
    LOBBY: 'border-green-800 text-green-600',
    DRAFTING: 'border-hacker-green text-hacker-green',
    EVALUATING: 'border-hacker-yellow text-hacker-yellow',
    RESULTS: 'border-hacker-red text-hacker-red',
  }

  const roleColors = {
    DEFENDER: 'text-blue-400',
    ATTACKER: 'text-hacker-red',
  }

  const isLow = timeRemaining != null && timeRemaining <= 30 && phase === 'DRAFTING'

  return (
    <header className="border-b border-green-900 bg-black bg-opacity-80 px-4 py-2 flex items-center justify-between text-xs gap-4 flex-wrap">
      {/* Left: Room + Status */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${connected ? 'bg-hacker-green' : 'bg-gray-600'}`} />
          <span className="text-green-700">ROOM:</span>
          <span className="text-hacker-green font-bold tracking-widest">{roomId}</span>
        </div>
        <div>
          <span className="text-green-700">PLAYERS:</span>
          <span className="text-hacker-green ml-1">{playerCount}/2</span>
        </div>
        {playMode === 'PASS_AND_PLAY' && (
          <div className="text-xs text-hacker-yellow border border-hacker-yellow px-1">
            🔄 P&amp;P
          </div>
        )}
      </div>

      {/* Center: Timer */}
      {phase === 'DRAFTING' && (
        <div className={`text-2xl font-bold tabular-nums transition-colors ${isLow ? 'text-hacker-red animate-pulse' : 'text-hacker-green'
          }`}>
          {formatTime(timeRemaining)}
        </div>
      )}

      {/* Right: Role + Phase + Leave */}
      <div className="flex items-center gap-4">
        {role && (
          <span className={`font-bold tracking-widest ${roleColors[role] || 'text-hacker-green'}`}>
            [{role}]
          </span>
        )}
        <span className={`phase-badge ${phaseColors[phase] || ''}`}>
          {phase}
        </span>
        <button
          onClick={onShowRules}
          className="text-green-800 hover:text-hacker-green transition-colors text-xs tracking-widest"
          title="How to play"
        >
          [?]
        </button>
        <button
          onClick={onLeave}
          className="text-green-900 hover:text-hacker-red transition-colors text-xs tracking-widest"
        >
          [EXIT]
        </button>
      </div>
    </header>
  )
}

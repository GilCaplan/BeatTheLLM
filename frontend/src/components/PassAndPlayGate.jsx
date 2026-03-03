/**
 * PassAndPlayGate — shown when it's the OTHER player's turn in pass-and-play mode.
 * Hides the screen until the current player is ready to hand over the device.
 */
export default function PassAndPlayGate({ waitingForRole, onReady }) {
  const roleLabel = waitingForRole === 'DEFENDER' ? '🛡 DEFENDER' : '⚔ ATTACKER'
  const roleColor = waitingForRole === 'DEFENDER' ? 'text-blue-400' : 'text-hacker-red'
  const borderColor = waitingForRole === 'DEFENDER' ? 'border-blue-500' : 'border-hacker-red'

  return (
    <div className="min-h-[70vh] flex items-center justify-center">
      <div className={`terminal-box text-center p-12 max-w-md ${borderColor}`}>
        <div className="text-4xl mb-4">🔒</div>
        <div className="text-green-700 text-sm mb-2 tracking-widest uppercase">
          Pass &amp; Play Mode
        </div>
        <div className={`text-3xl font-bold mb-4 ${roleColor}`}>
          {roleLabel}'s Turn
        </div>
        <p className="text-sm text-green-700 mb-8">
          Hand the device to the <span className={`font-bold ${roleColor}`}>{waitingForRole}</span>.
          <br />
          They should tap the button below when ready to enter their secret prompt.
        </p>
        <button onClick={onReady} className={`${waitingForRole === 'DEFENDER' ? 'btn-primary' : 'btn-danger'} px-10 py-3 text-lg`}>
          I'M READY
        </button>
        <div className="mt-6 text-green-900 text-xs">
          # The previous player's input is hidden. Do not look!
        </div>
      </div>
    </div>
  )
}

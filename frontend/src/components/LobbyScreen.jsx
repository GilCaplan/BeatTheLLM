import { useState, useEffect } from 'react'
import RulesScreen from './RulesScreen.jsx'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const DIFFICULTY_COLORS = {
  Easy: 'text-hacker-green border-hacker-green',
  Medium: 'text-hacker-yellow border-hacker-yellow',
  Hard: 'text-hacker-red border-hacker-red',
}

export default function LobbyScreen({ onCreateRoom, onJoinRoom }) {
  const [tab, setTab] = useState('create') // 'create' | 'join'
  const [playerName, setPlayerName] = useState('')
  const [roomCode, setRoomCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [showRules, setShowRules] = useState(false)

  // Room creation options
  const [playMode, setPlayMode] = useState('MULTIPLAYER') // 'MULTIPLAYER' | 'PASS_AND_PLAY' | 'SOLO'
  const [humanRole, setHumanRole] = useState('ATTACKER')  // for SOLO
  const [evalMode, setEvalMode] = useState('EXACT')       // 'EXACT' | 'JUDGE'
  const [scenarioMode, setScenarioMode] = useState('random') // 'random' | 'pick' | 'generate' | 'custom'
  const [selectedScenarioId, setSelectedScenarioId] = useState(null)
  const [scenarios, setScenarios] = useState([])
  const [scenariosLoading, setScenariosLoading] = useState(false)
  const [generateBrief, setGenerateBrief] = useState('')
  const [generatingScenario, setGeneratingScenario] = useState(false)
  const [generatedScenario, setGeneratedScenario] = useState(null)

  // Custom scenario form
  const [customForm, setCustomForm] = useState({
    title: '', system_setting: '', forbidden_words: '', difficulty: 'Medium', hint: ''
  })
  const [customSubmitting, setCustomSubmitting] = useState(false)
  const [customResult, setCustomResult] = useState(null)

  useEffect(() => {
    if (scenarioMode === 'pick' && scenarios.length === 0) {
      loadScenarios()
    }
  }, [scenarioMode])

  const loadScenarios = async () => {
    setScenariosLoading(true)
    try {
      const res = await fetch(`${API_BASE}/api/scenarios`)
      const data = await res.json()
      setScenarios(data.scenarios || [])
    } catch (e) {
      setError('Failed to load scenarios.')
    } finally {
      setScenariosLoading(false)
    }
  }

  const handleGenerateScenario = async () => {
    if (!generateBrief.trim()) return
    setGeneratingScenario(true)
    setGeneratedScenario(null)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/api/scenarios/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ brief: generateBrief.trim() }),
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Generation failed')
      }
      const scenario = await res.json()
      setGeneratedScenario(scenario)
    } catch (e) {
      setError(e.message)
    } finally {
      setGeneratingScenario(false)
    }
  }

  const handleSubmitCustomScenario = async () => {
    setCustomSubmitting(true)
    setCustomResult(null)
    setError(null)
    try {
      const words = customForm.forbidden_words
        .split(',')
        .map((w) => w.trim())
        .filter(Boolean)
      const res = await fetch(`${API_BASE}/api/scenarios/custom`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: customForm.title,
          system_setting: customForm.system_setting,
          forbidden_words: words,
          difficulty: customForm.difficulty,
          hint: customForm.hint,
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Submission failed')
      setCustomResult(data)
      if (data.approved) {
        // Reload scenarios and auto-select the new one
        await loadScenarios()
        setSelectedScenarioId(data.scenario_id)
        setScenarioMode('pick')
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setCustomSubmitting(false)
    }
  }

  const getEffectiveScenarioId = () => {
    if (scenarioMode === 'pick') return selectedScenarioId
    if (scenarioMode === 'generate' && generatedScenario?.id) return generatedScenario.id
    return null
  }

  const handleCreate = async () => {
    if (scenarioMode === 'pick' && !selectedScenarioId) { setError('Pick a scenario.'); return }
    if (scenarioMode === 'generate' && !generatedScenario) { setError('Generate a scenario first.'); return }
    setLoading(true)
    setError(null)
    try {
      await onCreateRoom(playerName.trim() || 'h4ck3r', getEffectiveScenarioId(), playMode, humanRole, evalMode)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const handleJoin = () => {
    if (!roomCode.trim()) { setError('Enter a room code.'); return }
    onJoinRoom(roomCode.trim(), playerName.trim() || 'h4ck3r')
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-4">
      {/* Title */}
      <div className="mb-8 text-center">
        <div className="text-xs tracking-[0.5em] text-green-700 mb-2 uppercase">
          &gt;&gt; Gil's Security Challenge &lt;&lt;
        </div>
        <h1
          className="text-5xl md:text-7xl font-bold glow-text mb-3 animate-pulse-green"
          style={{ textShadow: '0 0 20px #00ff41, 0 0 40px #00ff41' }}
        >
          JAILBREAK
        </h1>
        <h2 className="text-3xl md:text-5xl font-bold text-green-600">THE AI</h2>
        <div className="mt-3 text-green-700 text-sm">─── 2-Player Local Multiplayer ───</div>
      </div>

      <div className="w-full max-w-2xl space-y-4">
        {/* Tabs */}
        <div className="terminal-box">
          <div className="flex border-b border-green-900 mb-4">
            {['create', 'join'].map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`flex-1 py-2 text-sm tracking-widest uppercase transition-colors ${tab === t
                  ? 'text-hacker-green border-b-2 border-hacker-green'
                  : 'text-green-800 hover:text-green-600'
                  }`}
              >
                {t === 'create' ? '[ Create Room ]' : '[ Join Room ]'}
              </button>
            ))}
          </div>

          {/* Handle — hidden for Pass & Play (auto-assigned P1/P2) */}
          {(tab === 'join' || playMode !== 'PASS_AND_PLAY') && (
            <div className="mb-4">
              <label className="block text-xs text-green-600 mb-1 tracking-widest uppercase">
                &gt; Your Handle
              </label>
              <input
                type="text"
                value={playerName}
                onChange={(e) => setPlayerName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && (tab === 'create' ? handleCreate() : handleJoin())}
                placeholder="h4ck3r"
                maxLength={20}
                className="terminal-input"
              />
            </div>
          )}

          {tab === 'join' ? (
            <div className="mb-4">
              <label className="block text-xs text-green-600 mb-1 tracking-widest uppercase">
                &gt; Room Code
              </label>
              <input
                type="text"
                value={roomCode}
                onChange={(e) => setRoomCode(e.target.value.toUpperCase())}
                onKeyDown={(e) => e.key === 'Enter' && handleJoin()}
                placeholder="XXXXXXXX"
                maxLength={8}
                className="terminal-input tracking-widest text-center text-xl"
              />
            </div>
          ) : (
            <>
              {/* Play Mode */}
              <div className="mb-4">
                <label className="block text-xs text-green-600 mb-2 tracking-widest uppercase">
                  &gt; Play Mode
                </label>
                <div className="flex gap-2">
                  {[
                    { value: 'MULTIPLAYER', label: '⚡ Separate Screens', desc: 'Each player on their own device' },
                    { value: 'PASS_AND_PLAY', label: '🔄 Pass & Play', desc: 'Share one screen, take turns' },
                    { value: 'SOLO', label: '🤖 VS AI', desc: 'Play alone against an AI opponent' },
                  ].map((opt) => (
                    <button
                      key={opt.value}
                      onClick={() => setPlayMode(opt.value)}
                      className={`flex-1 p-3 border text-left text-xs transition-all ${playMode === opt.value
                        ? 'border-hacker-green bg-green-950 bg-opacity-30 text-hacker-green'
                        : 'border-green-900 text-green-700 hover:border-green-600'
                        }`}
                    >
                      <div className="font-bold mb-1">{opt.label}</div>
                      <div className="text-green-800">{opt.desc}</div>
                    </button>
                  ))}
                </div>

                {/* Role picker — only shown for SOLO mode */}
                {playMode === 'SOLO' && (
                  <div className="mt-3">
                    <label className="block text-xs text-green-600 mb-2 tracking-widest uppercase">
                      &gt; Your Role
                    </label>
                    <div className="flex gap-3">
                      {[
                        { value: 'DEFENDER', label: '🛡 Defender', desc: 'Craft the system prompt to protect the AI', color: 'border-blue-500 bg-blue-950 bg-opacity-30 text-blue-400' },
                        { value: 'ATTACKER', label: '⚔ Attacker', desc: 'Send prompts to make the AI slip up', color: 'border-hacker-red bg-red-950 bg-opacity-30 text-hacker-red' },
                      ].map((r) => (
                        <button
                          key={r.value}
                          onClick={() => setHumanRole(r.value)}
                          className={`flex-1 p-3 border text-left text-xs transition-all ${humanRole === r.value
                            ? r.color
                            : 'border-green-900 text-green-700 hover:border-green-600'
                            }`}
                        >
                          <div className="font-bold mb-1">{r.label}</div>
                          <div className="opacity-70">{r.desc}</div>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Evaluation Mode */}
              <div className="mb-4">
                <label className="block text-xs text-green-600 mb-2 tracking-widest uppercase">
                  &gt; Evaluation Mode
                </label>
                <div className="flex gap-2">
                  {[
                    { value: 'EXACT', label: '⚡ Word Match', desc: 'Fast exact string check (default)' },
                    { value: 'JUDGE', label: '🧠 + LLM Judge', desc: 'Semantic check + task completion' },
                  ].map((opt) => (
                    <button
                      key={opt.value}
                      onClick={() => setEvalMode(opt.value)}
                      className={`flex-1 p-3 border text-left text-xs transition-all ${evalMode === opt.value
                        ? 'border-hacker-green bg-green-950 bg-opacity-30 text-hacker-green'
                        : 'border-green-900 text-green-700 hover:border-green-600'
                        }`}
                    >
                      <div className="font-bold mb-1">{opt.label}</div>
                      <div className="text-green-800">{opt.desc}</div>
                    </button>
                  ))}
                </div>
                {evalMode === 'JUDGE' && (
                  <div className="mt-2 text-xs text-green-800 border border-green-900 p-2">
                    # LLM Judge checks if the AI expressed the forbidden concept semantically,
                    even without exact wording. Also penalises overly restrictive defence prompts
                    that cause the AI to refuse the benign task.
                  </div>
                )}
              </div>

              {/* Scenario Mode */}
              <div className="mb-4">
                <label className="block text-xs text-green-600 mb-2 tracking-widest uppercase">
                  &gt; Scenario
                </label>
                <div className="grid grid-cols-4 gap-2 text-xs mb-3">
                  {[
                    { value: 'random', label: '🎲 Random' },
                    { value: 'pick', label: '📋 Pick One' },
                    { value: 'generate', label: '🤖 AI Generate' },
                    { value: 'custom', label: '✏ Custom' },
                  ].map((opt) => (
                    <button
                      key={opt.value}
                      onClick={() => setScenarioMode(opt.value)}
                      className={`py-2 px-1 border text-center transition-all ${scenarioMode === opt.value
                        ? 'border-hacker-green bg-green-950 bg-opacity-30 text-hacker-green'
                        : 'border-green-900 text-green-700 hover:border-green-600'
                        }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>

                {/* Scenario Picker */}
                {scenarioMode === 'pick' && (
                  <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                    {scenariosLoading ? (
                      <div className="text-green-700 animate-pulse text-sm">Loading scenarios...</div>
                    ) : (
                      scenarios.map((s) => (
                        <button
                          key={s.id}
                          onClick={() => setSelectedScenarioId(s.id)}
                          className={`w-full text-left p-3 border text-xs transition-all ${selectedScenarioId === s.id
                            ? 'border-hacker-green bg-green-950 bg-opacity-40'
                            : 'border-green-900 hover:border-green-700'
                            }`}
                        >
                          <div className="flex justify-between items-start mb-1">
                            <span className="font-bold text-hacker-green">{s.title}</span>
                            <span className={`text-xs px-1 border ${DIFFICULTY_COLORS[s.difficulty] || 'text-green-600 border-green-700'}`}>
                              {s.difficulty}
                            </span>
                          </div>
                          <div className="text-green-700 line-clamp-2">{s.system_setting}</div>
                          <div className="text-hacker-red mt-1">
                            Forbidden: {s.forbidden_words?.join(', ')}
                          </div>
                        </button>
                      ))
                    )}
                  </div>
                )}

                {/* AI Generate */}
                {scenarioMode === 'generate' && (
                  <div className="space-y-3">
                    <div>
                      <label className="block text-xs text-green-700 mb-1">
                        Describe your scenario idea (1-2 sentences):
                      </label>
                      <textarea
                        value={generateBrief}
                        onChange={(e) => setGenerateBrief(e.target.value)}
                        rows={2}
                        maxLength={300}
                        placeholder="e.g. A medieval blacksmith who guards ancient forging secrets and never reveals their technique"
                        className="terminal-input text-sm"
                      />
                    </div>
                    <button
                      onClick={handleGenerateScenario}
                      disabled={generatingScenario || !generateBrief.trim()}
                      className={generateBrief.trim() && !generatingScenario ? 'btn-primary text-xs w-full' : 'btn-disabled text-xs w-full'}
                    >
                      {generatingScenario ? 'GENERATING...' : '> GENERATE SCENARIO'}
                    </button>
                    {generatedScenario && (
                      <div className="border border-hacker-green bg-green-950 bg-opacity-20 p-3 text-xs">
                        <div className="text-hacker-green font-bold mb-1">{generatedScenario.title}</div>
                        <div className="text-green-700 mb-2">{generatedScenario.system_setting}</div>
                        <div className="text-hacker-red">Forbidden: {generatedScenario.forbidden_words?.join(', ')}</div>
                        <div className="text-green-800 mt-1">Difficulty: {generatedScenario.difficulty}</div>
                      </div>
                    )}
                  </div>
                )}

                {/* Custom Scenario Form */}
                {scenarioMode === 'custom' && (
                  <div className="space-y-2 text-xs">
                    {[
                      { key: 'title', label: 'Title', placeholder: 'The Sneaky Librarian', type: 'input' },
                      { key: 'system_setting', label: 'System Setting (AI persona)', placeholder: 'You are a librarian who...', type: 'textarea' },
                      { key: 'forbidden_words', label: 'Forbidden Words (comma-separated)', placeholder: 'banned, restricted', type: 'input' },
                      { key: 'hint', label: 'Hint for Attacker (optional)', placeholder: 'Get the AI to reveal...', type: 'input' },
                    ].map((field) => (
                      <div key={field.key}>
                        <label className="block text-green-700 mb-1 tracking-widest uppercase">{field.label}</label>
                        {field.type === 'textarea' ? (
                          <textarea
                            rows={3}
                            value={customForm[field.key]}
                            onChange={(e) => setCustomForm((f) => ({ ...f, [field.key]: e.target.value }))}
                            placeholder={field.placeholder}
                            className="terminal-input text-sm"
                          />
                        ) : (
                          <input
                            type="text"
                            value={customForm[field.key]}
                            onChange={(e) => setCustomForm((f) => ({ ...f, [field.key]: e.target.value }))}
                            placeholder={field.placeholder}
                            className="terminal-input text-sm"
                          />
                        )}
                      </div>
                    ))}
                    <div>
                      <label className="block text-green-700 mb-1 tracking-widest uppercase">Difficulty</label>
                      <select
                        value={customForm.difficulty}
                        onChange={(e) => setCustomForm((f) => ({ ...f, difficulty: e.target.value }))}
                        className="terminal-input text-sm"
                      >
                        <option>Easy</option>
                        <option>Medium</option>
                        <option>Hard</option>
                      </select>
                    </div>
                    <button
                      onClick={handleSubmitCustomScenario}
                      disabled={customSubmitting}
                      className={!customSubmitting ? 'btn-primary text-xs w-full' : 'btn-disabled text-xs w-full'}
                    >
                      {customSubmitting ? 'SUBMITTING...' : '> SUBMIT SCENARIO'}
                    </button>
                    {customResult && (
                      <div className={`border p-2 text-xs ${customResult.approved ? 'border-hacker-green text-hacker-green' : 'border-hacker-yellow text-hacker-yellow'}`}>
                        {customResult.message}
                        {customResult.approved && <span className="ml-2">→ Scenario added to picker!</span>}
                      </div>
                    )}
                    <div className="text-green-900 text-xs">
                      # Submissions are reviewed for safety. Prompt injections are automatically rejected.
                    </div>
                  </div>
                )}
              </div>
            </>
          )}

          {/* Error */}
          {error && (
            <div className="text-hacker-red text-sm mb-3 border border-hacker-red p-2">
              [ERROR] {error}
            </div>
          )}

          {/* Action Button */}
          <button
            onClick={tab === 'create' ? handleCreate : handleJoin}
            disabled={loading}
            className={loading ? 'btn-disabled w-full mt-2' : 'btn-primary w-full mt-2'}
          >
            {loading
              ? 'INITIALIZING...'
              : tab === 'create'
              ? playMode === 'PASS_AND_PLAY'
                ? '> SPAWN ROOM (PASS & PLAY)'
                : playMode === 'SOLO'
                ? `> SPAWN ROOM (VS AI — ${humanRole})`
                : '> SPAWN ROOM'
              : '> INFILTRATE'}
          </button>

          <button
            onClick={() => setShowRules(true)}
            className="w-full mt-2 text-green-800 hover:text-hacker-green text-xs tracking-widest transition-colors py-1"
          >
            [?] HOW TO PLAY
          </button>

          {/* How it works */}
          <div className="mt-5 text-green-900 text-xs leading-relaxed">
            <p className="mb-1"># HOW IT WORKS:</p>
            <p>&nbsp;&nbsp;[DEFENDER] → craft a system prompt to protect the AI</p>
            <p>&nbsp;&nbsp;[ATTACKER] → send prompts to make the AI say the forbidden phrase</p>
            {tab === 'create' && (
              <p className="mt-2 text-green-800">
                # {playMode === 'PASS_AND_PLAY'
                  ? 'Pass & Play: share one screen, players take turns in private'
                  : playMode === 'SOLO'
                  ? `VS AI: you play ${humanRole === 'ATTACKER' ? 'ATTACKER vs an AI Defender' : 'DEFENDER vs an AI Attacker'}`
                  : 'Multiplayer: share the room code with your opponent'}
              </p>
            )}
          </div>
        </div>
      </div>

      {showRules && <RulesScreen onClose={() => setShowRules(false)} />}
    </div>
  )
}

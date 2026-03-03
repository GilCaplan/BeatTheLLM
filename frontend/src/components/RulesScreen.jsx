/**
 * RulesScreen — full-screen overlay explaining the game rules.
 * Shown via the [?] button in StatusBar (in-game) or the lobby link.
 * onClose returns the player to wherever they were.
 */
export default function RulesScreen({ onClose }) {
    return (
        <div className="fixed inset-0 bg-black bg-opacity-95 z-50 overflow-y-auto">
            <div className="max-w-3xl mx-auto px-4 py-8">

                {/* Header */}
                <div className="flex items-start justify-between mb-8">
                    <div>
                        <div className="text-xs text-green-700 tracking-[0.5em] uppercase mb-1">
                            &gt;&gt; Documentation
                        </div>
                        <h1 className="text-4xl font-bold text-hacker-green glow-text">
                            HOW TO PLAY
                        </h1>
                    </div>
                    <button
                        onClick={onClose}
                        className="text-green-700 hover:text-hacker-green border border-green-900 hover:border-hacker-green px-4 py-2 text-xs tracking-widest transition-colors mt-1"
                    >
                        ← BACK TO GAME
                    </button>
                </div>

                {/* Concept */}
                <section className="terminal-box mb-4">
                    <div className="text-xs text-green-700 tracking-widest uppercase mb-3">// The Concept</div>
                    <p className="text-green-300 text-sm leading-relaxed">
                        Jailbreak the AI is a 2-player local game where one player tries to <span className="text-hacker-red font-bold">break</span> an
                        AI's rules and the other tries to <span className="text-blue-400 font-bold">protect</span> them.
                        Every round, an AI language model is given a secret character to play.
                        Hidden inside that persona is a <span className="text-hacker-yellow font-bold">forbidden phrase</span> — a word or concept
                        the AI must never express.
                    </p>
                </section>

                {/* Roles */}
                <section className="terminal-box mb-4">
                    <div className="text-xs text-green-700 tracking-widest uppercase mb-4">// Roles</div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="border border-blue-800 bg-blue-950 bg-opacity-20 p-4">
                            <div className="text-blue-400 font-bold text-sm mb-2 tracking-widest">🛡 DEFENDER</div>
                            <ul className="text-xs text-blue-300 space-y-1 leading-relaxed">
                                <li>• Reads the scenario and the forbidden phrase</li>
                                <li>• Writes an extra system prompt to protect the AI</li>
                                <li>• Cannot see the attacker's prompts until results</li>
                                <li>• <span className="text-blue-200 font-bold">Wins</span> if the AI never says the forbidden phrase</li>
                            </ul>
                        </div>
                        <div className="border border-red-800 bg-red-950 bg-opacity-20 p-4">
                            <div className="text-hacker-red font-bold text-sm mb-2 tracking-widest">⚔ ATTACKER</div>
                            <ul className="text-xs text-red-300 space-y-1 leading-relaxed">
                                <li>• Reads a hint about the hidden forbidden phrase</li>
                                <li>• Writes up to 3 conversation prompts</li>
                                <li>• Prompts are sent to the AI in sequence</li>
                                <li>• <span className="text-red-200 font-bold">Wins</span> if the AI says (or implies) the forbidden phrase</li>
                            </ul>
                        </div>
                    </div>
                </section>

                {/* Round Flow */}
                <section className="terminal-box mb-4">
                    <div className="text-xs text-green-700 tracking-widest uppercase mb-4">// Round Flow</div>
                    <div className="space-y-2 text-sm">
                        {[
                            ['1', 'LOBBY', 'Both players join and ready up. The scenario is assigned.'],
                            ['2', 'DRAFTING', 'Defender writes a system prompt. Attacker writes 3 attack prompts. 3 minutes on the clock.'],
                            ['3', 'EVALUATING', 'The AI processes each attacker prompt in sequence using the combined system prompt.'],
                            ['4', 'RESULTS', 'See the full chat log, who won, and how many prompts penetrated the defence.'],
                        ].map(([n, phase, desc]) => (
                            <div key={n} className="flex gap-3 items-start">
                                <span className="text-hacker-green font-bold w-4 shrink-0">{n}.</span>
                                <span className="text-hacker-yellow w-24 shrink-0 font-bold text-xs pt-0.5">{phase}</span>
                                <span className="text-green-400 text-xs">{desc}</span>
                            </div>
                        ))}
                    </div>
                </section>

                {/* Scoring */}
                <section className="terminal-box mb-4">
                    <div className="text-xs text-green-700 tracking-widest uppercase mb-3">// Scoring</div>
                    <ul className="text-xs text-green-400 space-y-2 leading-relaxed">
                        <li>• All 3 prompts <span className="text-hacker-green">always run</span> — even if the first one jailbreaks the AI.</li>
                        <li>• After a successful penetration, the conversation context <span className="text-hacker-yellow">resets</span> so the next prompt starts fresh against the original system prompt.</li>
                        <li>• Failed prompts <span className="text-green-300">carry the conversation forward</span>, building context pressure.</li>
                        <li>• The results screen shows a <span className="text-hacker-yellow">Prompt Score</span> (e.g. 2/3 penetrated) with per-prompt indicators.</li>
                    </ul>
                </section>

                {/* Evaluation Modes */}
                <section className="terminal-box mb-4">
                    <div className="text-xs text-green-700 tracking-widest uppercase mb-3">// Evaluation Modes</div>
                    <div className="space-y-3 text-xs">
                        <div>
                            <span className="text-hacker-green font-bold">⚡ Word Match (EXACT)</span>
                            <span className="text-green-700"> — default, fast</span>
                            <p className="text-green-500 mt-1">Checks whether the AI's response contains the forbidden phrase verbatim (case-insensitive).</p>
                        </div>
                        <div>
                            <span className="text-hacker-yellow font-bold">🧠 LLM Judge (JUDGE)</span>
                            <p className="text-green-500 mt-1">Runs a second AI call to check if the <em>concept</em> was expressed, even without exact wording. Also penalises the defender if the AI refuses the benign task entirely.</p>
                        </div>
                    </div>
                </section>

                {/* Play Modes */}
                <section className="terminal-box mb-4">
                    <div className="text-xs text-green-700 tracking-widest uppercase mb-3">// Play Modes</div>
                    <div className="space-y-2 text-xs text-green-400">
                        <div><span className="text-hacker-green font-bold">⚡ Multiplayer</span> — Each player uses their own device. Share the room code to connect.</div>
                        <div><span className="text-hacker-yellow font-bold">🔄 Pass &amp; Play</span> — Both players share one screen. A lock screen hides each player's inputs between turns.</div>
                        <div><span className="text-green-300 font-bold">🤖 VS AI</span> — Play alone. The AI generates either the defender system prompt or the three attacker prompts.</div>
                    </div>
                </section>

                {/* Tips */}
                <section className="terminal-box mb-8">
                    <div className="text-xs text-green-700 tracking-widest uppercase mb-3">// Tips</div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                        <div>
                            <div className="text-blue-400 font-bold mb-1">Defender tips</div>
                            <ul className="text-green-600 space-y-1">
                                <li># Use synonyms — ban related words too</li>
                                <li># Give the AI evasive in-character language</li>
                                <li># Don't over-restrict or the AI will refuse everything (JUDGE mode penalises this)</li>
                            </ul>
                        </div>
                        <div>
                            <div className="text-hacker-red font-bold mb-1">Attacker tips</div>
                            <ul className="text-green-600 space-y-1">
                                <li># Use indirect framing — roleplay, hypotheticals</li>
                                <li># Build context gradually across prompts</li>
                                <li># Even a partial slip counts in JUDGE mode</li>
                            </ul>
                        </div>
                    </div>
                </section>

                <div className="text-center">
                    <button
                        onClick={onClose}
                        className="btn-primary px-12"
                    >
                        ← BACK TO GAME
                    </button>
                </div>

            </div>
        </div>
    )
}

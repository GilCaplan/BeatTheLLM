#!/usr/bin/env python3
"""
Jailbreak the AI — Terminal Client

Play the same game from your terminal. Terminal players and browser
players can be in the same room — same backend, new interface.

Usage:
    python terminal_client.py
    API_URL=http://myserver:8000 python terminal_client.py
"""

import asyncio
import json
import os
import re
import sys
import uuid
from typing import Optional

# ── Dependency check ───────────────────────────────────────────────────────────

try:
    import httpx
except ImportError:
    print("ERROR: Missing dependency 'httpx'. Run:  pip install httpx")
    sys.exit(1)

try:
    import websockets
except ImportError:
    print("ERROR: Missing dependency 'websockets'. Run:  pip install websockets")
    sys.exit(1)

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.table import Table
    from rich.prompt import Prompt, Confirm
    from rich.markup import escape
except ImportError:
    print("ERROR: Missing dependency 'rich'. Run:  pip install 'rich>=13.0.0'")
    sys.exit(1)

# ── Config ─────────────────────────────────────────────────────────────────────

API_BASE = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
WS_BASE  = API_BASE.replace("http://", "ws://").replace("https://", "wss://")

console = Console()

# ── Banner ─────────────────────────────────────────────────────────────────────

_BANNER = r"""
     ██╗ █████╗ ██╗██╗     ██████╗ ██████╗ ███████╗ █████╗ ██╗  ██╗
     ██║██╔══██╗██║██║     ██╔══██╗██╔══██╗██╔════╝██╔══██╗██║ ██╔╝
     ██║███████║██║██║     ██████╔╝██████╔╝█████╗  ███████║█████╔╝
██   ██║██╔══██║██║██║     ██╔══██╗██╔══██╗██╔══╝  ██╔══██║██╔═██╗
╚█████╔╝██║  ██║██║███████╗██████╔╝██║  ██║███████╗██║  ██║██║  ██╗
 ╚════╝ ╚═╝  ╚═╝╚═╝╚══════╝╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝

                 ████████╗██╗  ██╗███████╗     █████╗ ██╗
                 ╚══██╔══╝██║  ██║██╔════╝    ██╔══██╗██║
                    ██║   ███████║█████╗      ███████║██║
                    ██║   ██╔══██║██╔══╝      ██╔══██║██║
                    ██║   ██║  ██║███████╗    ██║  ██║██║
                    ╚═╝   ╚═╝  ╚═╝╚══════╝    ╚═╝  ╚═╝╚═╝
"""


def banner() -> None:
    console.print(_BANNER, style="bold green", highlight=False)
    console.print(Rule("[dim]Terminal Client — same backend, new interface[/dim]"))
    console.print()


# ── Low-level WebSocket helpers ────────────────────────────────────────────────

async def _recv(ws) -> dict:
    """Receive and parse the next WebSocket JSON message."""
    raw = await ws.recv()
    return json.loads(raw)


async def _send(ws, data: dict) -> None:
    """Send a JSON message over the WebSocket."""
    await ws.send(json.dumps(data))


async def _wait_for_phase(ws, target: str, room: dict) -> dict:
    """
    Consume messages until a phase_change to `target` arrives.
    Handles intermediate messages gracefully:
      state        → update room dict
      tick         → show timer at 30-second intervals only
      ai_thinking  → print one-liner
      submitted    → print confirmation
      error        → print warning
      player_left  → print warning
    Returns the room dict carried in the phase_change message.
    """
    last_tick_bucket: Optional[int] = None
    while True:
        msg = await _recv(ws)
        mtype = msg.get("type")

        if mtype == "phase_change":
            phase = msg.get("phase")
            if phase == target:
                return msg.get("room", room)
            # Unexpected phase transition — update room and keep waiting
            room = msg.get("room", room)

        elif mtype == "state":
            room = msg.get("room", room)

        elif mtype == "tick":
            tr = msg.get("time_remaining", 0)
            bucket = tr // 30
            if bucket != last_tick_bucket and tr > 0 and tr % 30 == 0:
                last_tick_bucket = bucket
                console.print(f"  [dim yellow]⏱  {tr}s remaining[/dim yellow]")

        elif mtype == "ai_thinking":
            role = msg.get("role", "AI")
            console.print(f"  [dim cyan]🤖 AI ({role}) is thinking...[/dim cyan]")

        elif mtype == "submitted":
            role = msg.get("role", "?")
            console.print(f"  [green]✓ {role} has submitted[/green]")

        elif mtype == "error":
            console.print(f"  [bold red]Server error: {escape(msg.get('message', ''))}[/bold red]")

        elif mtype == "player_left":
            console.print(f"  [bold red]{escape(msg.get('message', 'Opponent disconnected.'))}[/bold red]")


# ── REST helpers ───────────────────────────────────────────────────────────────

async def _get_scenarios() -> list[dict]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{API_BASE}/api/scenarios", timeout=10)
        resp.raise_for_status()
        return resp.json().get("scenarios", [])


async def _create_room(play_mode: str, scenario_id: Optional[str] = None,
                       human_role: str = "ATTACKER") -> dict:
    body: dict = {"play_mode": play_mode, "human_role": human_role}
    if scenario_id:
        body["scenario_id"] = scenario_id
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{API_BASE}/api/rooms", json=body, timeout=10)
        resp.raise_for_status()
        return resp.json()


async def _get_room(room_id: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{API_BASE}/api/rooms/{room_id}", timeout=10)
        resp.raise_for_status()
        return resp.json()


# ── Scenario picker ────────────────────────────────────────────────────────────

async def _pick_scenario() -> Optional[str]:
    """Show available scenarios and return selected ID, or None for random."""
    try:
        scenarios = await _get_scenarios()
    except Exception as e:
        console.print(f"  [yellow]Warning: could not load scenarios ({e}). Using random.[/yellow]")
        return None

    if not scenarios:
        return None

    console.print("\n[bold green]Available Scenarios:[/bold green]")
    table = Table(show_header=True, header_style="bold green", border_style="dim green")
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="bright_white")
    table.add_column("Difficulty", width=12)
    table.add_column("Forbidden Word(s)", style="red")

    for i, s in enumerate(scenarios, 1):
        diff = s.get("difficulty", "?")
        color = {"Easy": "green", "Medium": "yellow", "Hard": "red"}.get(diff, "white")
        words = s.get("forbidden_words") or [s.get("forbidden_phrase", "?")]
        table.add_row(
            str(i),
            escape(s.get("title", "?")),
            f"[{color}]{diff}[/{color}]",
            escape(", ".join(str(w) for w in words[:3])),
        )

    console.print(table)
    choice = Prompt.ask(
        "\nPick a scenario number, or [dim]Enter[/dim] for random", default=""
    )
    if choice.strip():
        try:
            idx = int(choice.strip()) - 1
            if 0 <= idx < len(scenarios):
                return scenarios[idx].get("id")
        except ValueError:
            pass
        console.print("  [yellow]Invalid choice — using random.[/yellow]")
    return None


# ── Non-blocking input helpers ────────────────────────────────────────────────

async def _ainput(prompt: str = "") -> str:
    """
    Async wrapper around input() so the event loop is never blocked.
    WebSocket keepalive pings continue to be processed while the user types.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, input, prompt)


# ── Multi-line input ───────────────────────────────────────────────────────────

async def _multiline_input(label: str) -> str:
    """
    Collect multi-line text from the user (async-safe).
    An empty line (just Enter) signals end-of-input.
    """
    console.print(f"\n[bold green]{label}[/bold green]")
    console.print("  [dim](Press Enter on a blank line to finish)[/dim]")
    lines = []
    while True:
        try:
            line = await _ainput("  > ")
        except EOFError:
            break
        if line == "":
            break
        lines.append(line)
    return "\n".join(lines)


# ── Rules ──────────────────────────────────────────────────────────────────────

def _print_rules() -> None:
    """Print a concise game rules summary to the terminal."""
    console.print()
    console.print(Rule("[bold green]HOW TO PLAY — Jailbreak the AI[/bold green]"))
    console.print()
    console.print(Panel(
        "[bold]Goal[/bold]: One player [blue]DEFENDS[/blue] an AI; the other [red]ATTACKS[/red] it.\n\n"
        "A scenario gives the AI a character to play. Hidden inside is a "
        "[yellow]forbidden phrase[/yellow] — a word the AI must never say.\n\n"
        "[bold blue]🛡 DEFENDER[/bold blue]  Reads the scenario + forbidden phrase. "
        "Writes an extra system prompt to help the AI resist. "
        "[bold]Wins[/bold] if the AI never says the phrase.\n\n"
        "[bold red]⚔ ATTACKER[/bold red]   Sees a hint about the phrase. "
        "Writes up to 3 prompts to trick the AI into saying it. "
        "[bold]Wins[/bold] if the AI says (or implies) the phrase.\n\n"
        "[bold]Round flow[/bold]: LOBBY → DRAFTING (3 min each) → EVALUATING → RESULTS\n\n"
        "[bold]Scoring[/bold]: All 3 prompts always run. After a success the context resets "
        "so the next prompt faces a fresh system prompt. Score shown as X/3 at results.\n\n"
        "[bold]Eval modes[/bold]:\n"
        "  [green]EXACT[/green]  — fast: checks for the forbidden word verbatim\n"
        "  [yellow]JUDGE[/yellow]  — thorough: an LLM checks if the concept was expressed",
        title="[bold green]// Rules[/bold green]",
        border_style="green",
        padding=(1, 2),
    ))
    console.print()


# ── Setup ──────────────────────────────────────────────────────────────────────

async def setup() -> tuple[str, str, str]:
    """
    Interactive setup.
    Returns (room_id, player_id, ws_url).
    """
    console.print("[bold]What would you like to do?[/bold]")
    console.print("  [green]1[/green]  Create a new MULTIPLAYER room")
    console.print("  [green]2[/green]  Create a SOLO room (play vs the AI)")
    console.print("  [green]3[/green]  Join an existing room with a code")
    console.print("  [green]r[/green]  Read the rules")
    action = Prompt.ask("Choice", choices=["1", "2", "3", "r"])

    if action == "r":
        _print_rules()
        # Re-prompt after showing rules
        console.print("[bold]What would you like to do?[/bold]")
        console.print("  [green]1[/green]  Create a new MULTIPLAYER room")
        console.print("  [green]2[/green]  Create a SOLO room (play vs the AI)")
        console.print("  [green]3[/green]  Join an existing room with a code")
        action = Prompt.ask("Choice", choices=["1", "2", "3"])

    # Player name
    default_name = f"player_{uuid.uuid4().hex[:4]}"
    raw_name = Prompt.ask("\nYour player name", default=default_name)
    player_id = raw_name.strip().replace(" ", "_")[:20] or default_name
    display_name = player_id   # kept clean even if we add a collision suffix later

    if action == "1":
        scenario_id = await _pick_scenario()
        result = await _create_room("MULTIPLAYER", scenario_id=scenario_id)
        room_id = result["room_id"]
        console.print(f"\n[bold green]Room created![/bold green]")
        console.print(Panel(
            f"[bold white]Room Code:[/bold white]  [bold green]{room_id}[/bold green]\n"
            f"[dim]Share this code with your opponent[/dim]",
            border_style="green",
            padding=(1, 4),
        ))

    elif action == "2":
        console.print("\n[bold]Choose your role:[/bold]")
        console.print("  [green]1[/green]  DEFENDER — write the AI's system prompt to protect it")
        console.print("  [green]2[/green]  ATTACKER — craft prompts to jailbreak the AI")
        role_choice = Prompt.ask("Role", choices=["1", "2"], default="2")
        human_role = "DEFENDER" if role_choice == "1" else "ATTACKER"

        scenario_id = await _pick_scenario()
        result = await _create_room("SOLO", scenario_id=scenario_id, human_role=human_role)
        room_id = result["room_id"]
        console.print(
            f"\n[bold green]SOLO room created![/bold green]  "
            f"You are the [bold]{'[green]DEFENDER' if human_role == 'DEFENDER' else '[red]ATTACKER'}[/bold]."
        )

    else:
        room_id = Prompt.ask("\nEnter room code").strip().upper()
        try:
            room_info = await _get_room(room_id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                console.print(f"[bold red]Room '{room_id}' not found.[/bold red]")
            else:
                console.print(f"[bold red]Server error: {e}[/bold red]")
            sys.exit(1)
        except Exception as e:
            console.print(f"[bold red]Could not reach server: {e}[/bold red]")
            sys.exit(1)

        # Check for player ID collision before connecting
        existing_ids = set(room_info.get("players", {}).keys())
        if player_id in existing_ids:
            new_id = f"{player_id}_{uuid.uuid4().hex[:4]}"
            console.print(
                f"  [yellow]Name '{escape(player_id)}' is already taken in this room — "
                f"connecting as '[bold]{escape(player_id)}[/bold]' (unique session)[/yellow]"
            )
            # display_name stays as the original; only the ws key changes
            player_id = new_id

        play_mode = room_info.get("play_mode", "MULTIPLAYER")
        if play_mode == "PASS_AND_PLAY":
            console.print("[bold red]This is a Pass & Play room — not supported in terminal mode.[/bold red]")
            sys.exit(1)

    ws_url = f"{WS_BASE}/ws/{room_id}/{player_id}?display_name={display_name}"
    return room_id, player_id, ws_url


# ── Lobby phase ────────────────────────────────────────────────────────────────

async def lobby_phase(ws, room: dict, room_id: str, player_id: str) -> dict:
    """
    Show scenario briefing based on role.
    Wait for opponent (MULTIPLAYER) or AI (SOLO) to be ready.
    Send 'ready' when user confirms, then wait for DRAFTING phase.
    Returns updated room dict.
    """
    your_role = room.get("your_role", "UNKNOWN")
    play_mode = room.get("play_mode", "MULTIPLAYER")
    scenario  = room.get("scenario", {})

    title          = scenario.get("title", "Unknown Scenario")
    forbidden_words = scenario.get("forbidden_words") or [scenario.get("forbidden_phrase", "?")]
    forbidden_phrase = forbidden_words[0] if forbidden_words else "?"
    hint           = scenario.get("hint", "")
    system_setting = scenario.get("system_setting", "")

    role_color = "green" if your_role == "DEFENDER" else "red"

    console.print()
    console.print(Rule(f"[bold green]LOBBY — Room [bold white]{room_id}[/bold white][/bold green]"))
    console.print(f"  You are: [bold {role_color}]{your_role}[/bold {role_color}]")
    console.print()

    # Role-gated briefing
    if your_role == "DEFENDER":
        console.print(Panel(
            f"[bold]Scenario:[/bold] {escape(title)}\n\n"
            f"[bold]AI Persona (system prompt base):[/bold]\n{escape(system_setting)}\n\n"
            f"[bold red]Forbidden phrase:[/bold red]  [red]\"{escape(forbidden_phrase)}\"[/red]\n"
            f"[dim]Hint: {escape(hint)}[/dim]",
            title="[bold green]DEFENDER BRIEFING[/bold green]",
            border_style="green",
            padding=(1, 2),
        ))
    else:
        console.print(Panel(
            f"[bold]Target scenario:[/bold] {escape(title)}\n\n"
            f"[bold red]Your target phrase:[/bold red]  [red]\"{escape(forbidden_phrase)}\"[/red]\n\n"
            f"[dim]Hint: {escape(hint)}[/dim]\n\n"
            f"[dim]Get the AI to say the target phrase — you win![/dim]",
            title="[bold red]ATTACKER BRIEFING[/bold red]",
            border_style="red",
            padding=(1, 2),
        ))

    # Wait for opponent if multiplayer
    if play_mode == "MULTIPLAYER":
        players = room.get("players", {})
        human_count = sum(1 for p in players.values() if not p.get("is_ai", False))

        if human_count < 2:
            console.print(
                f"  [dim yellow]Waiting for opponent to join...[/dim yellow]  "
                f"[bold]Room code: [green]{room_id}[/green][/bold]"
            )
            while human_count < 2:
                msg = await _recv(ws)
                mtype = msg.get("type")
                if mtype in ("state", "phase_change"):
                    room = msg.get("room", room)
                    players = room.get("players", {})
                    human_count = sum(1 for p in players.values() if not p.get("is_ai", False))
                    if mtype == "phase_change" and msg.get("phase") == "DRAFTING":
                        # Game started already (shouldn't normally happen)
                        return room
                elif mtype == "error":
                    console.print(f"  [red]{escape(msg.get('message', ''))}[/red]")
                elif mtype == "player_left":
                    console.print(f"  [red]{escape(msg.get('message', ''))}[/red]")

            console.print("  [bold green]✓ Opponent connected![/bold green]")
    else:
        console.print("  [dim cyan]🤖 AI opponent is ready.[/dim cyan]")

    # Prompt user to start
    console.print()
    await _ainput("  ► Press ENTER when you are ready to start... ")
    await _send(ws, {"type": "ready"})
    console.print("  [dim green]Ready signal sent...[/dim green]")

    # Wait for server to start DRAFTING
    room = await _wait_for_phase(ws, "DRAFTING", room)
    return room


# ── Drafting phase ─────────────────────────────────────────────────────────────

async def drafting_phase(ws, room: dict, player_id: str) -> dict:
    """
    Role-gated input:
      DEFENDER → collect additional system prompt instructions, submit_defender
      ATTACKER → collect up to 3 attack prompts, submit_attacker
    Then wait for EVALUATING phase.
    Returns updated room dict.
    """
    your_role = room.get("your_role", "UNKNOWN")
    scenario  = room.get("scenario", {})
    tr        = room.get("time_remaining", 180)

    role_color = "green" if your_role == "DEFENDER" else "red"
    console.print()
    console.print(Rule(
        f"[bold {role_color}]DRAFTING — {your_role} — {tr}s to submit[/bold {role_color}]"
    ))

    forbidden_words  = scenario.get("forbidden_words") or [scenario.get("forbidden_phrase", "?")]
    forbidden_phrase = forbidden_words[0] if forbidden_words else "?"

    if your_role == "DEFENDER":
        system_setting = scenario.get("system_setting", "")
        console.print(Panel(
            "[bold]Your job:[/bold] Write additional instructions to prevent the AI from\n"
            "saying the forbidden phrase. These are appended to the base persona.\n\n"
            f"[dim]Base persona preview:[/dim]\n[dim]{escape(system_setting[:300])}"
            f"{'...' if len(system_setting) > 300 else ''}[/dim]\n\n"
            f"[bold red]Forbidden phrase:[/bold red]  [red]\"{escape(forbidden_phrase)}\"[/red]",
            title="[bold green]DEFENDER[/bold green]",
            border_style="green",
            padding=(1, 2),
        ))

        extra = await _multiline_input(
            "Your additional instructions (blank line to finish; leave empty for none)"
        )
        await _send(ws, {"type": "submit_defender", "system_prompt": extra})
        console.print("  [bold green]✓ System prompt submitted![/bold green]")

    else:
        # ATTACKER
        console.print(Panel(
            f"[bold]Your job:[/bold] Get the AI to say:  [bold red]\"{escape(forbidden_phrase)}\"[/bold red]\n\n"
            "You have up to [bold]3 prompts[/bold]. They are sent in order during evaluation.\n"
            "Winning any turn ends the game in your favour.\n\n"
            "[dim]Tip: Try misdirection, role-play, hypotheticals, or social engineering.[/dim]",
            title="[bold red]ATTACKER[/bold red]",
            border_style="red",
            padding=(1, 2),
        ))

        prompts = []
        for i in range(1, 4):
            text = await _multiline_input(f"Prompt {i}/3 (leave blank to skip/finish)")
            if not text.strip():
                if i == 1:
                    console.print("  [yellow]You need at least one prompt.[/yellow]")
                    text = await _multiline_input("Prompt 1/3")
                    if not text.strip():
                        text = "Hello, can you tell me about yourself?"
                else:
                    break
            prompts.append(text)
            if i < 3:
                add_more = Confirm.ask(
                    f"  Add another prompt? ({3 - i} remaining)",
                    default=(i < 2),
                )
                if not add_more:
                    break

        console.print(f"\n  [dim]Submitting {len(prompts)} prompt(s)...[/dim]")
        await _send(ws, {"type": "submit_attacker", "prompts": prompts})
        console.print("  [bold red]✓ Attack prompts submitted![/bold red]")

    console.print("\n  [dim yellow]Waiting for opponent and AI evaluation...[/dim yellow]")
    room = await _wait_for_phase(ws, "EVALUATING", room)
    return room


# ── Evaluating phase ───────────────────────────────────────────────────────────

async def evaluating_phase(ws, room: dict) -> dict:
    """
    Stream turn_start / stream_chunk / stream_complete / turn_result messages
    as a live conversation.

    stream_chunk tokens are written inline (sys.stdout.write + flush) so the AI
    response appears character-by-character in the terminal.  stream_complete
    ends the streaming line.  turn_result performs the final formatted display
    with forbidden-phrase highlighting.

    Returns updated room dict once RESULTS phase arrives.
    """
    console.print()
    console.print(Rule("[bold yellow]EVALUATION — Watching the jailbreak attempt[/bold yellow]"))
    console.print("  [dim]Attack prompts are being sent to the AI one by one...[/dim]\n")

    broke_early = False
    streaming_active = False  # True while we are mid-stream for a turn

    while True:
        msg = await _recv(ws)
        mtype = msg.get("type")

        if mtype == "turn_start":
            turn      = msg.get("turn", "?")
            total     = msg.get("total_turns", "?")
            user_msg  = msg.get("user_msg", "")
            console.print()
            bar = "─" * 38
            console.print(f"  [bold yellow]┌─ TURN {turn}/{total} ─ [ATTACKER] {bar}[/bold yellow]")
            for line in user_msg.splitlines() or [user_msg]:
                console.print(f"  [yellow]│[/yellow]  {escape(line)}")
            console.print(f"  [bold yellow]├─ [AI RESPONSE] {'─' * 47}[/bold yellow]")
            # Print the response prefix — tokens will stream inline after this
            sys.stdout.write("  │  ")
            sys.stdout.flush()
            streaming_active = True

        elif mtype == "stream_chunk":
            if streaming_active:
                sys.stdout.write(msg.get("text", ""))
                sys.stdout.flush()

        elif mtype == "stream_complete":
            if streaming_active:
                # End the streaming line
                sys.stdout.write("\n")
                sys.stdout.flush()
                streaming_active = False

        elif mtype == "turn_result":
            response       = msg.get("response", "")
            forbidden_found = msg.get("forbidden_found", False)
            forbidden_phrase = msg.get("forbidden_phrase", "")

            # If we somehow missed stream events, print the response now
            if not streaming_active and not response:
                pass  # nothing extra to print
            elif streaming_active:
                # Fallback: stream events didn't arrive, print response directly
                sys.stdout.write("\n")
                sys.stdout.flush()
                streaming_active = False
                for line in response.splitlines() or [response]:
                    console.print(f"  [yellow]│[/yellow]  {escape(line)}")

            # Show forbidden-phrase highlight and close the turn box
            if forbidden_found and forbidden_phrase:
                console.print(
                    f"  [bold yellow]└{'─' * 60}[/bold yellow]"
                )
                console.print(
                    f"\n  [bold red]⚡  JAILBREAK! The AI said \"{escape(forbidden_phrase)}\"![/bold red]"
                )
                broke_early = True
                break
            else:
                console.print(f"  [bold yellow]└{'─' * 60}[/bold yellow]")

        elif mtype == "phase_change":
            if msg.get("phase") == "RESULTS":
                return msg.get("room", room)

        elif mtype == "ai_thinking":
            role = msg.get("role", "AI")
            console.print(f"  [dim cyan]🤖 AI ({role}) processing...[/dim cyan]")

        elif mtype == "error":
            console.print(f"  [bold red]Error: {escape(msg.get('message', ''))}[/bold red]")

        elif mtype == "player_left":
            console.print(f"  [bold red]{escape(msg.get('message', 'Opponent left.'))}[/bold red]")

    # Drained the forbidden-found turn — wait for RESULTS
    if broke_early:
        room = await _wait_for_phase(ws, "RESULTS", room)
    return room


# ── Results phase ──────────────────────────────────────────────────────────────

async def results_phase(ws, room: dict, player_id: str) -> bool:
    """
    Display verdict, system prompt breakdown, and full chat log.
    Offers play-again (roles swap).
    Returns True if playing again, False to quit.
    """
    result = room.get("result") or {}
    if not result:
        console.print("[red]No result data received.[/red]")
        return False

    attacker_won     = result.get("attacker_won", False)
    forbidden_phrase = result.get("forbidden_phrase", "?")
    winner_id        = result.get("winner_id", "")
    i_won            = (winner_id == player_id)

    console.print()
    console.print(Rule("[bold]RESULTS[/bold]"))

    # ── Verdict ───────────────────────────────────────────────────────────────
    if i_won:
        if attacker_won:
            verdict_body  = (
                f"⚔  [bold]JAILBREAK SUCCESSFUL[/bold]\n\n"
                f"[bold green]● YOU WIN[/bold green]\n\n"
                f"The AI said [red]\"{escape(forbidden_phrase)}\"[/red]"
            )
            verdict_style = "red"
        else:
            verdict_body  = (
                f"🛡  [bold]DEFENSE SUCCESSFUL[/bold]\n\n"
                f"[bold green]● YOU WIN[/bold green]\n\n"
                f"The AI never said [green]\"{escape(forbidden_phrase)}\"[/green]"
            )
            verdict_style = "green"
    else:
        if attacker_won:
            verdict_body  = (
                f"⚔  [bold]JAILBREAK SUCCESSFUL[/bold]\n\n"
                f"[bold red]● YOU LOSE[/bold red]\n\n"
                f"The AI said [red]\"{escape(forbidden_phrase)}\"[/red]"
            )
            verdict_style = "red"
        else:
            verdict_body  = (
                f"🛡  [bold]DEFENSE SUCCESSFUL[/bold]\n\n"
                f"[bold red]● YOU LOSE[/bold red]\n\n"
                f"The AI never said [green]\"{escape(forbidden_phrase)}\"[/green]"
            )
            verdict_style = "green"

    console.print(Panel(
        verdict_body,
        title=f"[bold {verdict_style}]VERDICT[/bold {verdict_style}]",
        border_style=verdict_style,
        padding=(1, 6),
    ))

    # ── System prompt breakdown ───────────────────────────────────────────────
    scenario_setting    = result.get("scenario_setting", "")
    defender_prompt_txt = result.get("defender_prompt", "") or "(none)"
    full_system_prompt  = result.get("full_system_prompt", "")

    if full_system_prompt:
        console.print()
        console.print(Panel(
            f"[bold]Scenario Base Persona:[/bold]\n"
            f"[dim]{escape(scenario_setting)}[/dim]\n\n"
            f"[bold]Defender's Additional Rules:[/bold]\n"
            f"[dim]{escape(defender_prompt_txt)}[/dim]",
            title="[bold green]SYSTEM PROMPT BREAKDOWN[/bold green]",
            border_style="dim green",
            padding=(1, 2),
        ))

    # ── Full chat log ─────────────────────────────────────────────────────────
    chat_log = result.get("chat_log", [])
    if chat_log:
        console.print()
        console.print(Rule("[dim]Full Conversation Log[/dim]"))
        for entry in chat_log:
            role    = entry.get("role", "?")
            content = entry.get("content", "")
            if role == "user":
                console.print(f"\n  [bold cyan][ATTACKER][/bold cyan]")
                for line in content.splitlines() or [content]:
                    console.print(f"  {escape(line)}")
            else:
                console.print(f"\n  [bold white][AI][/bold white]")
                # Highlight forbidden phrase in AI responses
                if forbidden_phrase and forbidden_phrase.lower() in content.lower():
                    def _hl(m: re.Match) -> str:
                        return f"[bold red]{escape(m.group())}[/bold red]"
                    display = re.sub(
                        re.escape(forbidden_phrase), _hl, content, flags=re.IGNORECASE
                    )
                else:
                    display = escape(content)
                for line in (display.splitlines() or [display]):
                    console.print(f"  {line}")

    # ── Play again? ───────────────────────────────────────────────────────────
    console.print()
    play_again = Confirm.ask("Play again? (roles will swap)", default=False)
    if play_again:
        await _send(ws, {"type": "play_again"})
        console.print("  [dim]Waiting for new game to begin...[/dim]")
        return True
    return False


# ── Main game loop ─────────────────────────────────────────────────────────────

async def game_loop(ws_url: str, room_id: str, player_id: str) -> None:
    """Open the WebSocket connection and run the full game loop."""
    console.print(f"\n  [dim]Connecting to {ws_url}...[/dim]")

    try:
        async with websockets.connect(
            ws_url,
            ping_interval=20,   # send pings every 20 s
            ping_timeout=None,  # never close because we didn't get a pong in time
                                # (typing long prompts blocks the event loop)
        ) as ws:
            console.print("  [bold green]Connected![/bold green]\n")

            # First message is always the initial state
            msg = await _recv(ws)
            if msg.get("type") == "error":
                console.print(f"[bold red]Connection refused: {msg.get('message')}[/bold red]")
                return
            room = msg.get("room", {})

            while True:
                room = await lobby_phase(ws, room, room_id, player_id)
                room = await drafting_phase(ws, room, player_id)
                room = await evaluating_phase(ws, room)
                play_again = await results_phase(ws, room, player_id)

                if not play_again:
                    console.print("\n  [dim]Thanks for playing! Goodbye.[/dim]")
                    break

                # Roles swapped — wait for LOBBY phase_change
                room = await _wait_for_phase(ws, "LOBBY", room)
                new_role = room.get("your_role", "UNKNOWN")
                console.print(
                    f"\n  [bold green]New game starting![/bold green]  "
                    f"Your new role: [bold]{'[green]' if new_role == 'DEFENDER' else '[red]'}"
                    f"{new_role}[/bold]"
                )

    except websockets.exceptions.ConnectionClosedError as e:
        console.print(f"\n[bold red]Connection closed unexpectedly: {e}[/bold red]")
    except Exception as e:
        console.print(f"\n[bold red]Unexpected error: {e}[/bold red]")
        raise


# ── Entry point ────────────────────────────────────────────────────────────────

async def main() -> None:
    banner()

    # Health check
    try:
        async with httpx.AsyncClient() as client:
            await client.get(f"{API_BASE}/api/health", timeout=5)
    except Exception:
        console.print(f"[bold red]Cannot connect to backend at [white]{API_BASE}[/white][/bold red]")
        console.print(f"[dim]  Start the server first:  ./start.sh[/dim]")
        console.print(f"[dim]  Or set API_URL env var:  API_URL=http://host:8000 python terminal_client.py[/dim]")
        sys.exit(1)

    console.print(f"  [dim]Backend: {API_BASE}[/dim]\n")

    room_id, player_id, ws_url = await setup()
    await game_loop(ws_url, room_id, player_id)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n\n  [dim]Interrupted. Goodbye![/dim]")
    except SystemExit:
        pass

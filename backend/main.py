"""
FastAPI WebSocket server for Jailbreak the AI.

REST endpoints:
  POST /api/rooms                    - Create a new room
  GET  /api/rooms/{id}               - Get room info
  GET  /api/scenarios                - List all available scenarios
  POST /api/scenarios/generate       - AI-generate a scenario from a brief
  POST /api/scenarios/custom         - Submit a custom scenario

WebSocket endpoint:
  WS /ws/{room_id}/{player_id}  - Game event stream

WebSocket message protocol (JSON):
  Client -> Server:
    { "type": "ready" }
    { "type": "submit_defender", "system_prompt": "..." }
    { "type": "submit_attacker", "prompts": ["...", "..."] }
    { "type": "play_again" }
    { "type": "pass_and_play_done" }

  Server -> Client:
    { "type": "state",          "room": {...} }
    { "type": "phase_change",   "phase": "...", "room": {...} }
    { "type": "tick",           "time_remaining": N }
    { "type": "submitted",      "role": "DEFENDER"|"ATTACKER" }
    { "type": "turn_start",     "turn": N, "total_turns": N, "user_msg": "..." }
    { "type": "stream_chunk",   "turn": N, "text": "..." }
    { "type": "stream_complete","turn": N }
    { "type": "turn_result",    "turn": N, "response": "...", "forbidden_found": bool }
    { "type": "player_left",    "message": "..." }
    { "type": "error",          "message": "..." }
"""
import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from game_state import (
    EvalMode,
    GamePhase,
    GameResult,
    PlayMode,
    PlayerRole,
    RoomManager,
    room_manager,
    DRAFTING_SECONDS,
)
from llm_handler import (
    check_forbidden_phrase,
    create_turn_streamer,
    judge_output,
    run_inference_multiturn,
    mock_think,
    MOCK_LLM,
    MOCK_STREAM_DELAY,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Connection Manager ────────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, dict[str, WebSocket]] = {}

    def add(self, room_id: str, player_id: str, ws: WebSocket) -> None:
        self._connections.setdefault(room_id, {})[player_id] = ws

    def remove(self, room_id: str, player_id: str) -> None:
        room_conns = self._connections.get(room_id, {})
        room_conns.pop(player_id, None)
        if not room_conns:
            self._connections.pop(room_id, None)

    async def send(self, room_id: str, player_id: str, data: dict) -> None:
        ws = self._connections.get(room_id, {}).get(player_id)
        if ws:
            try:
                await ws.send_json(data)
            except Exception:
                pass

    async def broadcast(self, room_id: str, data: dict) -> None:
        """Broadcast identical payload to every connected player."""
        for ws in list(self._connections.get(room_id, {}).values()):
            try:
                await ws.send_json(data)
            except Exception:
                pass

    async def broadcast_state(self, room_id: str, room, msg_type: str = "state") -> None:
        """
        Broadcast personalised room state to each player so every client
        always receives their own your_role / your_ready fields.
        """
        conns = self._connections.get(room_id, {})
        for pid, ws in list(conns.items()):
            try:
                await ws.send_json({
                    "type": msg_type,
                    "room": room.to_dict(pid),
                })
            except Exception:
                pass

    async def broadcast_phase(self, room_id: str, phase: str, room) -> None:
        conns = self._connections.get(room_id, {})
        for pid, ws in list(conns.items()):
            try:
                await ws.send_json({
                    "type": "phase_change",
                    "phase": phase,
                    "room": room.to_dict(pid),
                })
            except Exception:
                pass

    def get_player_ids(self, room_id: str) -> list[str]:
        return list(self._connections.get(room_id, {}).keys())


conn_manager = ConnectionManager()

# ─── Timer Logic ──────────────────────────────────────────────────────────────

_timer_tasks: dict[str, asyncio.Task] = {}
_ai_tasks: dict[str, asyncio.Task] = {}


async def _run_timer(room_id: str, rm: RoomManager) -> None:
    room = rm.get_room(room_id)
    if room is None:
        return
    while room.time_remaining > 0:
        await asyncio.sleep(1)
        room.time_remaining -= 1
        await conn_manager.broadcast(room_id, {
            "type": "tick",
            "time_remaining": room.time_remaining,
        })
    logger.info(f"Room {room_id}: timer expired, triggering evaluation")
    await _evaluate_room(room_id, rm)


def _start_timer(room_id: str, rm: RoomManager) -> None:
    if room_id in _timer_tasks:
        _timer_tasks[room_id].cancel()
    _timer_tasks[room_id] = asyncio.create_task(_run_timer(room_id, rm))


def _stop_timer(room_id: str) -> None:
    t = _timer_tasks.pop(room_id, None)
    if t:
        t.cancel()


# ─── AI Opponent Auto-Submit ───────────────────────────────────────────────────

async def _ai_auto_submit(room_id: str, rm: RoomManager) -> None:
    """After a thinking delay, the AI generates and submits its content."""
    from ai_opponent import (
        AI_PLAYER_ID, generate_ai_defender_prompt, generate_ai_attacker_prompts, ai_think
    )

    room = rm.get_room(room_id)
    if room is None:
        return

    ai_state = room.players.get(AI_PLAYER_ID)
    if ai_state is None:
        return

    # Broadcast that AI is "thinking"
    await conn_manager.broadcast(room_id, {
        "type": "ai_thinking",
        "role": ai_state.role.value,
    })

    await ai_think(ai_state.role.value)

    room = rm.get_room(room_id)
    if room is None or room.phase != GamePhase.DRAFTING:
        return

    scenario = room.scenario
    loop = asyncio.get_event_loop()
    if ai_state.role == PlayerRole.DEFENDER:
        # Run synchronous LLM call in a thread so we don't block the event loop
        prompt = await loop.run_in_executor(None, generate_ai_defender_prompt, scenario)
        rm.submit_defender_prompt(room_id, AI_PLAYER_ID, prompt)
        logger.info(f"Room {room_id}: AI Defender generated prompt ({len(prompt)} chars)")
    else:
        prompts = await loop.run_in_executor(None, generate_ai_attacker_prompts, scenario)
        rm.submit_attacker_prompts(room_id, AI_PLAYER_ID, prompts)
        logger.info(f"Room {room_id}: AI Attacker generated {len(prompts)} prompts")

    ai_state.ready = True

    await conn_manager.broadcast_state(room_id, room)
    await _check_both_submitted(room_id, rm)


# ─── Multi-turn Streaming Evaluation ──────────────────────────────────────────

async def _evaluate_room(room_id: str, rm: RoomManager) -> None:
    """
    Run per-turn LLM inference and stream results to both players in real-time.
    Each (user_msg → AI response) pair is broadcast as turn_start / turn_result
    so both clients can watch the conversation unfold live.
    """
    room = rm.get_room(room_id)
    if room is None or room.phase == GamePhase.RESULTS:
        return

    _stop_timer(room_id)
    room.phase = GamePhase.EVALUATING
    await conn_manager.broadcast_phase(room_id, "EVALUATING", room)

    defender = room.get_defender()
    attacker = room.get_attacker()

    scenario_setting = room.scenario.get("system_setting", "You are a helpful assistant.")
    defender_extra = defender.system_prompt if defender else ""
    attacker_prompts = (attacker.attacker_prompts if attacker and attacker.attacker_prompts
                        else ["Hello, what can you tell me?"])

    forbidden_words = room.scenario.get("forbidden_words", [])
    forbidden_phrase = room.scenario.get("forbidden_phrase", forbidden_words[0] if forbidden_words else "")
    benign_task = room.scenario.get("benign_task", "Respond helpfully to the user's question.")
    eval_mode = room.eval_mode

    # Always start with the scenario's base setting, then layer the defender's
    # custom restrictions on top. This ensures the character persona is preserved.
    if defender_extra.strip():
        full_system_prompt = f"{scenario_setting}\n\n=== DEFENDER'S ADDITIONAL RULES ===\n{defender_extra.strip()}"
    else:
        full_system_prompt = scenario_setting
    system_prompt = full_system_prompt

    total_turns = len(attacker_prompts)
    logger.info(
        f"Room {room_id}: evaluating {total_turns} turn(s) | eval={eval_mode.value} | "
        f"defender_extra={len(defender_extra)} chars | "
        f"full_system_prompt={len(full_system_prompt)} chars"
    )
    logger.info(f"Room {room_id}: system prompt preview: {full_system_prompt[:120]!r}...")

    chat_log = []
    attacker_won = False
    final_output = ""
    overall_concept_breached = False
    overall_task_completed = True

    loop = asyncio.get_event_loop()

    # ── Stream turn by turn ────────────────────────────────────────────────
    conversation: list[dict] = []

    for turn_idx, user_msg in enumerate(attacker_prompts, start=1):
        # Build conversation history up to this turn
        conversation.append({"role": "user", "content": user_msg})

        # Announce the attacker's prompt
        await conn_manager.broadcast(room_id, {
            "type": "turn_start",
            "turn": turn_idx,
            "total_turns": total_turns,
            "user_msg": user_msg,
        })

        # ── Stream tokens from the LLM ─────────────────────────────────────
        # create_turn_streamer is a blocking generator; we bridge it to asyncio
        # via a Queue so the event loop stays unblocked between chunks.
        import queue as _queue
        token_queue: _queue.Queue = _queue.Queue()
        DONE_SENTINEL = object()

        def _stream_worker(sys_p, conv):
            """Run in a thread: push chunks into token_queue."""
            try:
                for chunk in create_turn_streamer(sys_p, list(conv)):
                    token_queue.put(chunk)
            except Exception as exc:
                token_queue.put(f"[STREAM ERROR: {exc}]")
            finally:
                token_queue.put(DONE_SENTINEL)

        stream_future = loop.run_in_executor(
            None, _stream_worker, system_prompt, conversation.copy()
        )

        response_parts: list[str] = []
        while True:
            # Poll the queue with a tiny timeout so asyncio tasks can intersperse
            try:
                chunk = await loop.run_in_executor(
                    None, token_queue.get, True, 0.05   # block=True, timeout=0.05s
                )
            except _queue.Empty:
                continue

            if chunk is DONE_SENTINEL:
                break

            response_parts.append(chunk)
            await conn_manager.broadcast(room_id, {
                "type": "stream_chunk",
                "turn": turn_idx,
                "text": chunk,
            })

        await stream_future  # ensure the thread has fully exited

        response = "".join(response_parts)

        # Signal to clients that streaming for this turn is finished
        await conn_manager.broadcast(room_id, {
            "type": "stream_complete",
            "turn": turn_idx,
        })

        # ── Step 1: exact string match (always) ───────────────────────────
        word_found = check_forbidden_phrase(response, forbidden_phrase)

        # ── Step 2: LLM semantic judge (JUDGE mode only, when step 1 missed)
        concept_breached_this_turn = word_found
        task_completed_this_turn = True

        if eval_mode == EvalMode.JUDGE and not word_found:
            verdict = await loop.run_in_executor(
                None, judge_output, response, forbidden_words, benign_task
            )
            concept_breached_this_turn = verdict["concept_breached"]
            task_completed_this_turn = verdict["task_completed"]

        # Attacker wins if concept breached OR AI refused the benign task
        turn_attacker_won = concept_breached_this_turn or not task_completed_this_turn
        if turn_attacker_won:
            attacker_won = True

        # Track overall judge results for telemetry / result display
        if concept_breached_this_turn:
            overall_concept_breached = True
        if not task_completed_this_turn:
            overall_task_completed = False

        conversation.append({"role": "assistant", "content": response})
        chat_log.append({"role": "user", "content": user_msg})
        chat_log.append({"role": "assistant", "content": response})
        final_output = response

        # Broadcast the complete AI response for this turn (backward compat)
        await conn_manager.broadcast(room_id, {
            "type": "turn_result",
            "turn": turn_idx,
            "total_turns": total_turns,
            "response": response,
            "user_msg": user_msg,
            "forbidden_found": word_found,
            "concept_breached": concept_breached_this_turn,
            "task_completed": task_completed_this_turn,
            "forbidden_phrase": forbidden_phrase,
        })

        # Short pause between turns so UI can animate
        await asyncio.sleep(0.4)

        if turn_attacker_won:
            break  # Early exit — attacker already won

    # ── Determine winner ───────────────────────────────────────────────────
    winner_id = loser_id = None
    if attacker and defender:
        winner_id = attacker.player_id if attacker_won else defender.player_id
        loser_id  = defender.player_id if attacker_won else attacker.player_id

    result = GameResult(
        attacker_won=attacker_won,
        llm_output=final_output,
        forbidden_phrase=forbidden_phrase,
        chat_log=chat_log,
        scenario_setting=scenario_setting,
        defender_prompt=defender_extra,
        full_system_prompt=full_system_prompt,
        winner_id=winner_id,
        loser_id=loser_id,
        concept_breached=overall_concept_breached,
        task_completed=overall_task_completed,
    )
    rm.set_result(room_id, result)

    # ── Telemetry ──────────────────────────────────────────────────────────
    try:
        from telemetry import log_match
        log_match(
            scenario_id=room.scenario.get("id", "unknown"),
            defender_prompt=defender_extra,
            attacker_prompts=attacker_prompts,
            ai_response=final_output,
            concept_breached=overall_concept_breached,
            task_completed=overall_task_completed,
            winner=winner_id or ("attacker" if attacker_won else "defender"),
        )
    except Exception as _tel_err:
        logger.warning(f"Telemetry logging failed (non-fatal): {_tel_err}")

    await conn_manager.broadcast_phase(room_id, "RESULTS", room)


# ─── FastAPI App ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Jailbreak the AI server starting up")
    from scenario_manager import load_scenarios
    load_scenarios()
    yield
    logger.info("Jailbreak the AI server shutting down")
    for t in list(_timer_tasks.values()) + list(_ai_tasks.values()):
        t.cancel()


app = FastAPI(title="Jailbreak the AI", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Pydantic Models ──────────────────────────────────────────────────────────

class CreateRoomRequest(BaseModel):
    scenario_id: str | None = None
    play_mode: str = "MULTIPLAYER"
    human_role: str = "ATTACKER"   # for SOLO mode: "DEFENDER" or "ATTACKER"
    eval_mode: str = "EXACT"       # "EXACT" (word match only) or "JUDGE" (+ LLM judge)


class CustomScenarioRequest(BaseModel):
    title: str
    system_setting: str
    forbidden_words: list[str]
    difficulty: str = "Medium"
    hint: str = ""


class GenerateScenarioRequest(BaseModel):
    brief: str


# ─── REST Endpoints ───────────────────────────────────────────────────────────

@app.post("/api/rooms")
async def create_room(body: CreateRoomRequest = None):
    if body is None:
        body = CreateRoomRequest()

    try:
        mode = PlayMode(body.play_mode)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid play_mode: {body.play_mode}")

    try:
        eval_mode = EvalMode(body.eval_mode)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid eval_mode: {body.eval_mode}")

    if mode == PlayMode.SOLO:
        try:
            human_role = PlayerRole(body.human_role)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid human_role: {body.human_role}")
        room = room_manager.create_solo_room(
            human_role=human_role, scenario_id=body.scenario_id, eval_mode=eval_mode
        )
    else:
        room = room_manager.create_room(
            scenario_id=body.scenario_id, play_mode=mode, eval_mode=eval_mode
        )

    return {
        "room_id": room.room_id,
        "scenario": room.scenario,
        "play_mode": mode.value,
        "eval_mode": eval_mode.value,
    }


@app.get("/api/rooms/{room_id}")
async def get_room(room_id: str):
    room = room_manager.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    return room.to_dict()


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/scenarios")
async def list_scenarios_endpoint():
    from scenario_manager import list_scenarios
    return {"scenarios": list_scenarios()}


@app.post("/api/scenarios/custom")
async def submit_custom_scenario(body: CustomScenarioRequest):
    from scenario_manager import submit_custom_scenario
    result = submit_custom_scenario({
        "title": body.title,
        "system_setting": body.system_setting,
        "forbidden_words": body.forbidden_words,
        "difficulty": body.difficulty,
        "hint": body.hint,
    })
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.to_dict()


@app.post("/api/scenarios/generate")
async def generate_scenario(body: GenerateScenarioRequest):
    import re as _re
    from llm_handler import run_inference
    from scenario_manager import _INJECTION_RE, submit_custom_scenario, _normalize_scenario

    brief = body.brief.strip()
    if not brief or len(brief) > 300:
        raise HTTPException(status_code=400, detail="Brief must be 1-300 characters.")
    if _INJECTION_RE.search(brief):
        raise HTTPException(status_code=400, detail="Brief contains disallowed content.")

    system = (
        "You are a creative game designer for a party game called 'Jailbreak the AI'. "
        "Given a brief idea, output a scenario as a JSON object with keys: "
        '"title", "system_setting", "forbidden_words" (array), "difficulty" (Easy/Medium/Hard), "hint". '
        "Output ONLY valid JSON."
    )
    try:
        raw = run_inference(system, [f"Brief: {brief}"])
        match = _re.search(r'\{[\s\S]+\}', raw)
        if not match:
            raise ValueError("No JSON in output")
        generated = json.loads(match.group())
    except Exception as e:
        logger.warning(f"LLM generation failed: {e} — using template")
        generated = {
            "title": f"The {brief[:40]}",
            "system_setting": f"You are {brief}. Stay in character at all times.",
            "forbidden_words": ["secret"],
            "difficulty": "Medium",
            "hint": "Get the AI to reveal something it's hiding!",
        }

    result = submit_custom_scenario(generated, use_llm_validation=False)
    if result.success and result.approved:
        generated["id"] = result.scenario_id
    return _normalize_scenario(generated)


# ─── WebSocket Endpoint ───────────────────────────────────────────────────────

@app.websocket("/ws/{room_id}/{player_id}")
async def websocket_endpoint(ws: WebSocket, room_id: str, player_id: str):
    await ws.accept()

    # Optional display_name query param — lets clients pass a human-friendly
    # label even when the player_id has a collision-avoidance suffix appended.
    display_name = ws.query_params.get("display_name", "").strip() or player_id

    try:
        room, role = room_manager.join_room(room_id, player_id, display_name=display_name)
    except ValueError as e:
        await ws.send_json({"type": "error", "message": str(e)})
        await ws.close()
        return

    conn_manager.add(room_id, player_id, ws)
    logger.info(f"WS connected: player={player_id} display={display_name} room={room_id} role={role.value}")

    # Send personalised initial state to this player
    await ws.send_json({"type": "state", "room": room.to_dict(player_id)})

    # Broadcast updated state (with personalisation) to all players
    await conn_manager.broadcast_state(room_id, room)

    # SOLO: if AI is already in room and we now have 2 players, auto-start becomes possible
    # (AI is pre-ready, so the moment the human clicks ready, all_ready() is true)

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = msg.get("type")

            # ── ready ──────────────────────────────────────────────────────
            if msg_type == "ready":
                room_manager.set_ready(room_id, player_id, True)
                room = room_manager.get_room(room_id)
                await conn_manager.broadcast_state(room_id, room)

                if room.all_ready() and room.phase == GamePhase.LOBBY:
                    room_manager.start_drafting(room_id)
                    _start_timer(room_id, room_manager)
                    await conn_manager.broadcast_phase(room_id, "DRAFTING", room)

                    # SOLO: kick off AI auto-submit in background
                    if room.play_mode == PlayMode.SOLO:
                        t = asyncio.create_task(_ai_auto_submit(room_id, room_manager))
                        _ai_tasks[room_id] = t

            # ── submit_defender ────────────────────────────────────────────
            elif msg_type == "submit_defender":
                system_prompt = msg.get("system_prompt", "")
                try:
                    room_manager.submit_defender_prompt(room_id, player_id, system_prompt)
                    room = room_manager.get_room(room_id)
                    room.players[player_id].ready = True
                    stored = room.players[player_id].system_prompt
                    logger.info(
                        f"Room {room_id}: DEFENDER '{player_id}' locked in prompt "
                        f"({len(stored)} chars): {stored[:80]!r}{'...' if len(stored) > 80 else ''}"
                    )
                    await ws.send_json({"type": "submitted", "role": "DEFENDER"})
                    await conn_manager.broadcast_state(room_id, room)
                    await _check_both_submitted(room_id, room_manager)
                except ValueError as e:
                    await ws.send_json({"type": "error", "message": str(e)})

            # ── submit_attacker ────────────────────────────────────────────
            elif msg_type == "submit_attacker":
                prompts = msg.get("prompts", [])
                try:
                    room_manager.submit_attacker_prompts(room_id, player_id, prompts)
                    room = room_manager.get_room(room_id)
                    room.players[player_id].ready = True
                    stored = room.players[player_id].attacker_prompts
                    logger.info(
                        f"Room {room_id}: ATTACKER '{player_id}' locked in {len(stored)} prompt(s): "
                        + " | ".join(f"{p[:60]!r}" for p in stored)
                    )
                    await ws.send_json({"type": "submitted", "role": "ATTACKER"})
                    await conn_manager.broadcast_state(room_id, room)
                    await _check_both_submitted(room_id, room_manager)
                except ValueError as e:
                    await ws.send_json({"type": "error", "message": str(e)})

            # ── pass_and_play_done ─────────────────────────────────────────
            elif msg_type == "pass_and_play_done":
                room = room_manager.get_room(room_id)
                if room and room.play_mode == PlayMode.PASS_AND_PLAY:
                    room_manager.advance_pass_and_play_turn(room_id)
                    await conn_manager.broadcast_state(room_id, room)

            # ── play_again ─────────────────────────────────────────────────
            elif msg_type == "play_again":
                room = room_manager.get_room(room_id)
                if room and room.phase == GamePhase.RESULTS:
                    from scenario_manager import get_random_scenario
                    from ai_opponent import AI_PLAYER_ID

                    room.scenario = get_random_scenario()
                    room.phase = GamePhase.LOBBY
                    room.result = None
                    room.time_remaining = DRAFTING_SECONDS
                    room.pass_and_play_turn = None
                    # eval_mode persists across rematches

                    for p in room.players.values():
                        if not p.is_ai:
                            p.ready = False
                            p.system_prompt = ""
                            p.attacker_prompts = []
                        # Swap roles
                        p.role = (
                            PlayerRole.ATTACKER if p.role == PlayerRole.DEFENDER
                            else PlayerRole.DEFENDER
                        )
                    # AI pre-marked ready for SOLO
                    if room.play_mode == PlayMode.SOLO and room.ai_player_id:
                        ai_state = room.players.get(room.ai_player_id)
                        if ai_state:
                            ai_state.ready = True

                    await conn_manager.broadcast_phase(room_id, "LOBBY", room)

            else:
                await ws.send_json({
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}",
                })

    except WebSocketDisconnect:
        logger.info(f"WS disconnected: player={player_id} room={room_id}")
        conn_manager.remove(room_id, player_id)
        room_manager.remove_player(room_id, player_id)
        remaining = conn_manager.get_player_ids(room_id)
        if remaining:
            await conn_manager.broadcast(room_id, {
                "type": "player_left",
                "message": "Your opponent disconnected.",
            })
        else:
            _stop_timer(room_id)
            t = _ai_tasks.pop(room_id, None)
            if t:
                t.cancel()


async def _check_both_submitted(room_id: str, rm: RoomManager) -> None:
    room = rm.get_room(room_id)
    if room is None or room.phase != GamePhase.DRAFTING:
        return
    defender = room.get_defender()
    attacker = room.get_attacker()
    if (
        defender and attacker
        and defender.ready and attacker.ready
        and defender.system_prompt
        and attacker.attacker_prompts
    ):
        logger.info(f"Room {room_id}: both submitted, evaluating now")
        await _evaluate_room(room_id, rm)

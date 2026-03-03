"""
Game State Manager: Handles rooms, roles, phases, and timers.

Phase flow:
  LOBBY -> DRAFTING -> EVALUATING -> RESULTS

Scenarios are loaded dynamically from scenario_manager (scenarios.json + SQLite).
"""
import asyncio
import uuid
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)

DRAFTING_SECONDS = 180  # 3 minutes per drafting phase
MAX_ATTACKER_PROMPTS = 3


class GamePhase(str, Enum):
    LOBBY = "LOBBY"
    DRAFTING = "DRAFTING"
    EVALUATING = "EVALUATING"
    RESULTS = "RESULTS"


class PlayerRole(str, Enum):
    DEFENDER = "DEFENDER"
    ATTACKER = "ATTACKER"


class PlayMode(str, Enum):
    MULTIPLAYER = "MULTIPLAYER"      # Two separate windows/devices
    PASS_AND_PLAY = "PASS_AND_PLAY"  # One screen, players take turns
    SOLO = "SOLO"                    # Human vs AI opponent


class EvalMode(str, Enum):
    EXACT = "EXACT"   # Step 1 only: case-insensitive exact string match (default, fast)
    JUDGE = "JUDGE"   # Step 1 + Step 2: string match then LLM semantic judge


@dataclass
class PlayerState:
    player_id: str
    display_name: str = ""   # human-readable label; defaults to player_id if not set
    role: Optional[PlayerRole] = None
    ready: bool = False
    is_ai: bool = False
    # Defender fields
    system_prompt: str = ""
    # Attacker fields
    attacker_prompts: list = field(default_factory=list)

    def __post_init__(self):
        if not self.display_name:
            self.display_name = self.player_id


@dataclass
class GameResult:
    attacker_won: bool
    llm_output: str          # final assistant message
    forbidden_phrase: str
    chat_log: list           # [{"role": "user"/"assistant", "content": str}]
    scenario_setting: str = ""    # the scenario's base system_setting
    defender_prompt: str = ""     # the defender's additional instructions
    full_system_prompt: str = ""  # combined prompt sent to the LLM
    winner_id: Optional[str] = None
    loser_id: Optional[str] = None
    # Judge fields (populated when eval_mode == JUDGE)
    concept_breached: bool = False   # semantic concept expressed in any turn
    task_completed: bool = True      # AI completed the benign task in all turns
    # Scoring
    prompts_succeeded: int = 0       # how many individual prompts penetrated the defence


@dataclass
class Room:
    room_id: str
    phase: GamePhase = GamePhase.LOBBY
    players: dict = field(default_factory=dict)   # player_id -> PlayerState
    scenario: dict = field(default_factory=dict)
    time_remaining: int = DRAFTING_SECONDS
    result: Optional[GameResult] = None
    play_mode: PlayMode = PlayMode.MULTIPLAYER
    eval_mode: EvalMode = EvalMode.EXACT
    # Pass-and-play: whose turn it is to look at the screen
    pass_and_play_turn: Optional[str] = None
    # Solo: the AI player's id (always __ai_bot__ when set)
    ai_player_id: Optional[str] = None
    _timer_task: Optional[asyncio.Task] = field(default=None, repr=False)

    def get_player_count(self) -> int:
        return len(self.players)

    def get_defender(self) -> Optional[PlayerState]:
        for p in self.players.values():
            if p.role == PlayerRole.DEFENDER:
                return p
        return None

    def get_attacker(self) -> Optional[PlayerState]:
        for p in self.players.values():
            if p.role == PlayerRole.ATTACKER:
                return p
        return None

    def all_ready(self) -> bool:
        return (
            len(self.players) == 2
            and all(p.ready for p in self.players.values())
        )

    def to_dict(self, requesting_player_id: str = None) -> dict:
        """Serialize room state for sending over WebSocket."""
        from ai_opponent import AI_PLAYER_ID, AI_DISPLAY_NAME
        players_info = {}
        for pid, p in self.players.items():
            players_info[pid] = {
                "role": p.role.value if p.role else None,
                "ready": p.ready,
                "is_ai": p.is_ai,
                "display_name": AI_DISPLAY_NAME if p.is_ai else p.display_name,
            }

        base = {
            "room_id": self.room_id,
            "phase": self.phase.value,
            "players": players_info,
            "scenario": self.scenario,
            "time_remaining": self.time_remaining,
            "play_mode": self.play_mode.value,
            "eval_mode": self.eval_mode.value,
            "pass_and_play_turn": self.pass_and_play_turn,
            "ai_player_id": self.ai_player_id,
            "result": None,
        }

        if self.result:
            base["result"] = {
                "attacker_won": self.result.attacker_won,
                "llm_output": self.result.llm_output,
                "forbidden_phrase": self.result.forbidden_phrase,
                "chat_log": self.result.chat_log,
                "scenario_setting": self.result.scenario_setting,
                "defender_prompt": self.result.defender_prompt,
                "full_system_prompt": self.result.full_system_prompt,
                "winner_id": self.result.winner_id,
                "loser_id": self.result.loser_id,
                "concept_breached": self.result.concept_breached,
                "task_completed": self.result.task_completed,
                "prompts_succeeded": self.result.prompts_succeeded,
            }

        if requesting_player_id and requesting_player_id in self.players:
            p = self.players[requesting_player_id]
            base["your_role"] = p.role.value if p.role else None
            base["your_ready"] = p.ready

        return base


class RoomManager:
    """Manages all active game rooms."""

    def __init__(self):
        self._rooms: dict[str, Room] = {}

    def create_room(
        self,
        scenario_id: Optional[str] = None,
        play_mode: PlayMode = PlayMode.MULTIPLAYER,
        eval_mode: EvalMode = EvalMode.EXACT,
    ) -> Room:
        from scenario_manager import get_random_scenario, get_scenario_by_id
        room_id = str(uuid.uuid4())[:8].upper()
        scenario = (get_scenario_by_id(scenario_id) if scenario_id else None) or get_random_scenario()
        room = Room(room_id=room_id, scenario=scenario, play_mode=play_mode, eval_mode=eval_mode)
        self._rooms[room_id] = room
        logger.info(
            f"Room {room_id} created | scenario='{scenario['id']}' | "
            f"mode={play_mode.value} | eval={eval_mode.value}"
        )
        return room

    def create_solo_room(
        self,
        human_role: PlayerRole = PlayerRole.ATTACKER,
        scenario_id: Optional[str] = None,
        eval_mode: EvalMode = EvalMode.EXACT,
    ) -> Room:
        """
        Create a SOLO room (human vs AI).
        The AI is pre-added with the opposite role; it is pre-marked ready.
        """
        from scenario_manager import get_random_scenario, get_scenario_by_id
        from ai_opponent import AI_PLAYER_ID

        room_id = str(uuid.uuid4())[:8].upper()
        scenario = (get_scenario_by_id(scenario_id) if scenario_id else None) or get_random_scenario()
        room = Room(room_id=room_id, scenario=scenario, play_mode=PlayMode.SOLO, eval_mode=eval_mode)
        room.ai_player_id = AI_PLAYER_ID

        ai_role = PlayerRole.ATTACKER if human_role == PlayerRole.DEFENDER else PlayerRole.DEFENDER
        room.players[AI_PLAYER_ID] = PlayerState(
            player_id=AI_PLAYER_ID, role=ai_role, ready=True, is_ai=True
        )
        self._rooms[room_id] = room
        logger.info(
            f"SOLO room {room_id} | human={human_role.value} ai={ai_role.value} | scenario='{scenario['id']}'"
        )
        return room

    def get_room(self, room_id: str) -> Optional[Room]:
        return self._rooms.get(room_id.upper())

    def join_room(self, room_id: str, player_id: str, display_name: str = "") -> tuple[Room, PlayerRole]:
        """
        Add a human player to a room.
        - MULTIPLAYER/PASS_AND_PLAY: first joiner = DEFENDER, second = ATTACKER.
        - SOLO: human gets the role not already taken by the AI.
        Raises ValueError if room is full or not in LOBBY.
        """
        from ai_opponent import AI_PLAYER_ID
        room = self.get_room(room_id)
        if room is None:
            raise ValueError(f"Room {room_id} not found.")

        human_count = sum(1 for p in room.players.values() if not p.is_ai)
        if human_count >= 2:
            raise ValueError(f"Room {room_id} is full.")
        if room.phase != GamePhase.LOBBY:
            raise ValueError(f"Room {room_id} game already started.")
        if player_id in room.players:
            raise ValueError(f"Player ID '{player_id}' is already in use in this room. Choose a different name.")

        if room.play_mode == PlayMode.SOLO and room.ai_player_id:
            ai_state = room.players.get(room.ai_player_id)
            role = (
                PlayerRole.DEFENDER if ai_state and ai_state.role == PlayerRole.ATTACKER
                else PlayerRole.ATTACKER
            )
        else:
            # Normal: first human = DEFENDER, second = ATTACKER
            existing_human_roles = {p.role for p in room.players.values() if not p.is_ai}
            role = PlayerRole.DEFENDER if PlayerRole.DEFENDER not in existing_human_roles else PlayerRole.ATTACKER

        room.players[player_id] = PlayerState(
            player_id=player_id,
            display_name=display_name or player_id,
            role=role,
        )
        logger.info(f"Player {player_id} ({display_name or player_id}) joined room {room_id} as {role.value}")
        return room, role

    def set_ready(self, room_id: str, player_id: str, ready: bool = True) -> Room:
        room = self.get_room(room_id)
        if room is None:
            raise ValueError(f"Room {room_id} not found.")
        if player_id not in room.players:
            raise ValueError(f"Player {player_id} not in room {room_id}.")
        room.players[player_id].ready = ready
        return room

    def submit_defender_prompt(self, room_id: str, player_id: str, system_prompt: str) -> None:
        room = self.get_room(room_id)
        if room is None:
            raise ValueError(f"Room {room_id} not found.")
        player = room.players.get(player_id)
        if player is None or player.role != PlayerRole.DEFENDER:
            raise ValueError(f"Player {player_id} is not the Defender.")
        player.system_prompt = system_prompt.strip()

    def submit_attacker_prompts(self, room_id: str, player_id: str, prompts: list[str]) -> None:
        room = self.get_room(room_id)
        if room is None:
            raise ValueError(f"Room {room_id} not found.")
        player = room.players.get(player_id)
        if player is None or player.role != PlayerRole.ATTACKER:
            raise ValueError(f"Player {player_id} is not the Attacker.")
        if len(prompts) > MAX_ATTACKER_PROMPTS:
            raise ValueError(f"Too many prompts. Max is {MAX_ATTACKER_PROMPTS}.")
        player.attacker_prompts = [p.strip() for p in prompts if p.strip()]

    def remove_player(self, room_id: str, player_id: str) -> None:
        room = self.get_room(room_id)
        if room and player_id in room.players:
            del room.players[player_id]
            logger.info(f"Player {player_id} removed from room {room_id}")
            if len(room.players) == 0:
                self._rooms.pop(room_id, None)
                logger.info(f"Room {room_id} deleted (empty)")

    def start_drafting(self, room_id: str) -> Room:
        room = self.get_room(room_id)
        if room is None:
            raise ValueError(f"Room {room_id} not found.")
        if len(room.players) < 2:
            raise ValueError("Need 2 players to start.")
        room.phase = GamePhase.DRAFTING
        room.time_remaining = DRAFTING_SECONDS
        for p in room.players.values():
            if not p.is_ai:
                p.ready = False
        if room.play_mode == PlayMode.PASS_AND_PLAY:
            defender = room.get_defender()
            room.pass_and_play_turn = defender.player_id if defender else None
        logger.info(f"Room {room_id} entering DRAFTING phase")
        return room

    def advance_pass_and_play_turn(self, room_id: str) -> Room:
        room = self.get_room(room_id)
        if room is None:
            raise ValueError(f"Room {room_id} not found.")
        pids = list(room.players.keys())
        if len(pids) == 2:
            current = room.pass_and_play_turn
            room.pass_and_play_turn = pids[1] if current == pids[0] else pids[0]
        # Give the incoming player a full fresh timer
        room.time_remaining = DRAFTING_SECONDS
        return room

    def set_result(self, room_id: str, result: GameResult) -> Room:
        room = self.get_room(room_id)
        if room is None:
            raise ValueError(f"Room {room_id} not found.")
        room.result = result
        room.phase = GamePhase.RESULTS
        logger.info(f"Room {room_id} -> RESULTS | attacker_won={result.attacker_won}")
        return room

    def delete_room(self, room_id: str) -> None:
        self._rooms.pop(room_id, None)


# Global singleton
room_manager = RoomManager()

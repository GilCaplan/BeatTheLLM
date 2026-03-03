"""
LLM Handler: Local HuggingFace model inference with auto device detection.

Device selection (automatic):
  1. MPS  — Apple Silicon (M1/M2/M3) via Metal
  2. CUDA — NVIDIA GPU
  3. CPU  — fallback

Set MOCK_LLM=1 to skip loading model weights entirely (for testing).

Default model: meta-llama/Llama-3.2-1B-Instruct  (already on your machine)
Override via LLM_MODEL env var in backend/.env

Public API:
  run_inference(system, [msgs])           — single call (for AI gen, scenario gen)
  run_inference_multiturn(system, [msgs]) — per-turn calls, returns list of responses
  check_forbidden_phrase(output, phrase)  — case-insensitive substring check
  mock_think(delay)                       — async sleep used during mock playback
"""
import asyncio
import logging
import os

from dotenv import load_dotenv

# Load .env before reading any env vars (existing shell vars still take precedence)
load_dotenv()

logger = logging.getLogger(__name__)

MOCK_LLM    = os.getenv("MOCK_LLM", "0") == "1"
MODEL_ID    = os.getenv("LLM_MODEL", "meta-llama/Llama-3.2-1B-Instruct")

# Mock thinking delay per turn (seconds) — makes live playback feel real
MOCK_TURN_DELAY = float(os.getenv("MOCK_TURN_DELAY", "1.2"))

_pipeline = None   # lazy-loaded HuggingFace pipeline
_use_messages_api = False  # True if model supports list-of-dicts input (Llama 3.2 style)


def _detect_device() -> str:
    """Return the best available torch device."""
    try:
        import torch
        if torch.backends.mps.is_available():
            logger.info("Device: MPS (Apple Silicon Metal)")
            return "mps"
        if torch.cuda.is_available():
            logger.info("Device: CUDA")
            return "cuda"
    except Exception:
        pass
    logger.info("Device: CPU")
    return "cpu"


def _get_pipeline():
    """Lazy-load the HuggingFace text-generation pipeline (singleton)."""
    global _pipeline, _use_messages_api
    if _pipeline is not None:
        return _pipeline

    logger.info(f"Loading model: {MODEL_ID} ...")
    device = _detect_device()

    from transformers import pipeline, AutoTokenizer

    # Check if the model has a chat template (Llama 3.2 Instruct, Qwen, Gemma-IT, etc.)
    try:
        tok = AutoTokenizer.from_pretrained(MODEL_ID)
        _use_messages_api = bool(getattr(tok, "chat_template", None))
    except Exception:
        _use_messages_api = False

    logger.info(f"Chat-template mode: {_use_messages_api}")

    # MPS doesn't support device_map="auto" — pass device directly instead
    import torch
    pipe_kwargs = {
        "model": MODEL_ID,
        "dtype": torch.float16 if device in ("mps", "cuda") else torch.float32,
    }
    if device == "mps":
        pipe_kwargs["device"] = "mps"
    else:
        pipe_kwargs["device_map"] = "auto"

    _pipeline = pipeline("text-generation", **pipe_kwargs)
    logger.info(f"Model loaded: {MODEL_ID}")
    return _pipeline


# ─── Inference helpers ────────────────────────────────────────────────────────

def _chat(pipe, system_prompt: str, conversation: list[dict]) -> str:
    """
    Run a single inference call given a full conversation list.
    conversation: [{"role": "user"|"assistant", "content": str}, ...]
    The last message must be from "user".

    Returns the assistant reply string.
    """
    if _use_messages_api:
        # Modern API: pass messages directly; pipeline applies chat template internally
        messages = [{"role": "system", "content": system_prompt}] + conversation
        output = pipe(
            messages,
            max_new_tokens=512,
            do_sample=True,
            temperature=0.7,
            top_p=0.9,
            return_full_text=False,
        )
        # Output format: [{"generated_text": [{"role":..., "content":...}, ...]}]
        generated = output[0]["generated_text"]
        if isinstance(generated, list):
            # Find the last assistant turn
            for turn in reversed(generated):
                if turn.get("role") == "assistant":
                    return turn["content"].strip()
            return str(generated[-1]).strip()
        return str(generated).strip()
    else:
        # Legacy ChatML string format (TinyLlama, older models)
        return _chat_chatml(pipe, system_prompt, conversation)


def _chat_chatml(pipe, system_prompt: str, conversation: list[dict]) -> str:
    """Build a ChatML string prompt and run inference."""
    parts = [f"<|system|>\n{system_prompt}</s>"]
    for msg in conversation:
        tag = "<|user|>" if msg["role"] == "user" else "<|assistant|>"
        parts.append(f"{tag}\n{msg['content']}</s>")
    parts.append("<|assistant|>")
    prompt = "\n".join(parts)

    output = pipe(
        prompt,
        max_new_tokens=256,
        do_sample=True,
        temperature=0.7,
        top_p=0.9,
        repetition_penalty=1.1,
        return_full_text=False,
    )
    return output[0]["generated_text"].strip()


# ─── Single-call inference (for scenario/AI prompt generation) ────────────────

def run_inference(system_prompt: str, user_messages: list[str]) -> str:
    """
    Run inference with all user messages in a single call.
    Used for scenario generation and AI opponent prompt crafting.
    Returns the final assistant response string.
    """
    if not user_messages:
        return ""

    if MOCK_LLM:
        return f"[MOCK] Received: '{user_messages[-1][:60]}'"

    pipe = _get_pipeline()
    conversation = []
    for i, msg in enumerate(user_messages):
        conversation.append({"role": "user", "content": msg})
        if i < len(user_messages) - 1:
            conversation.append({"role": "assistant", "content": "[continuing...]"})

    try:
        return _chat(pipe, system_prompt, conversation)
    except Exception as e:
        logger.error(f"run_inference failed: {e}")
        return f"[ERROR: {e}]"


# ─── Multi-turn inference (streams per turn to the frontend) ──────────────────

def run_inference_multiturn(system_prompt: str, user_messages: list[str]) -> list[str]:
    """
    Proper multi-turn inference: one LLM call per attacker prompt,
    building up conversation history with real AI responses so context
    carries through correctly.

    Returns a list of response strings, one per user message.
    """
    if not user_messages:
        return []

    if MOCK_LLM:
        return [
            f"[MOCK RESPONSE] I received your message: '{msg.lower()}'. I cannot help with that."
            for msg in user_messages
        ]

    pipe = _get_pipeline()
    responses = []
    conversation: list[dict] = []

    for user_msg in user_messages:
        conversation.append({"role": "user", "content": user_msg})
        try:
            response = _chat(pipe, system_prompt, conversation)
        except Exception as e:
            logger.error(f"run_inference_multiturn turn failed: {e}")
            response = f"[ERROR: {e}]"
        conversation.append({"role": "assistant", "content": response})
        responses.append(response)
        logger.debug(f"Turn {len(responses)}: {len(response)} chars")

    return responses


# ─── Forbidden phrase check ───────────────────────────────────────────────────

def check_forbidden_phrase(llm_output: str, forbidden_phrase: str) -> bool:
    """
    Case-insensitive check if the forbidden phrase appears in the LLM output.
    Returns True if found (Attacker wins), False otherwise (Defender wins).
    """
    return forbidden_phrase.lower() in llm_output.lower()


async def mock_think(delay: float = None):
    """Async sleep to simulate model thinking in MOCK mode."""
    await asyncio.sleep(delay if delay is not None else MOCK_TURN_DELAY)

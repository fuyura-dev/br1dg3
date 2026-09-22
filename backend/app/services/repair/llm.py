import time
from dataclasses import dataclass

from app.config import settings
from google import genai

client = genai.Client(api_key=settings.LLM_API_KEY)

GENERATION_CONFIG: dict = {
    "thinking_level": "medium",             # minimal | low | medium | high
    # "seed": 42,
    # "max_output_tokens": 8192,
}

# Transient failures (rate limit, overloaded, network) are retried. This is NOT a repair retry:
# a bad reply is never re-requested (the paper records the output without retries).
MAX_RETRIES = 3
RETRY_STATUS = {429, 500, 502, 503, 504}
RETRY_ERRORS = {"ReadTimeout", "ConnectTimeout", "ConnectError", "TimeoutException",
                "RemoteProtocolError", "NoResponseError"}


@dataclass
class LLMResult:
    text: str
    ok: bool                 # completed AND non-empty text (a truncated reply is NOT ok)
    status: str | None       # the interaction status, e.g. "completed", "incomplete"
    model: str
    prompt_tokens: int       # usage.total_input_tokens (system prompt included)
    completion_tokens: int   # usage.total_output_tokens
    thought_tokens: int      # usage.total_thought_tokens, billed like output: cost = completion + thought
    total_tokens: int
    latency_s: float         # of the successful request only
    attempts: int            # HTTP requests made for this call (1 unless a transient error was retried)


def _get(obj, name, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _text(interaction):
    """The reply text. `output_text` on current SDKs; older shapes are kept as fallbacks."""
    text = _get(interaction, "output_text")
    if text:
        return text
    outputs = _get(interaction, "outputs")                  # older SDK: interaction.outputs[-1].text
    if outputs:
        return _get(outputs[-1], "text", "") or ""
    steps = _get(interaction, "steps")                      # newer shape: steps[-1].content[*].text
    if steps:
        return "".join(_get(part, "text", "") or "" for part in (_get(steps[-1], "content") or []))
    return ""


def _is_transient(exc):
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    return code in RETRY_STATUS or type(exc).__name__ in RETRY_ERRORS


def generate(prompt) -> LLMResult:
    """prompt: anything with .system and .user (the Prompt from prompt.py)."""
    request = {
        "model": settings.LLM_MODEL,
        "system_instruction": prompt.system,
        "input": prompt.user,
        "store": False,                       # stateless: nothing is kept server-side between calls
    }
    if GENERATION_CONFIG:
        request["generation_config"] = GENERATION_CONFIG

    attempts = 0
    while True:
        attempts += 1
        started = time.perf_counter()
        try:
            interaction = client.interactions.create(**request)
            break
        except Exception as exc:
            if attempts > MAX_RETRIES or not _is_transient(exc):
                raise
            time.sleep(2 ** (attempts - 1))   # 1s, 2s, 4s
    latency = time.perf_counter() - started

    usage = _get(interaction, "usage")
    text = _text(interaction)
    status = _get(interaction, "status")
    status = str(getattr(status, "value", status)).lower() if status is not None else None
    prompt_tokens = _get(usage, "total_input_tokens", 0) or 0
    completion_tokens = _get(usage, "total_output_tokens", 0) or 0
    thought_tokens = _get(usage, "total_thought_tokens", 0) or 0

    return LLMResult(
        text=text,
        ok=status == "completed" and bool(text.strip()),
        status=status,
        model=settings.LLM_MODEL,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        thought_tokens=thought_tokens,
        total_tokens=_get(usage, "total_tokens", 0) or (prompt_tokens + completion_tokens + thought_tokens),
        latency_s=round(latency, 3),
        attempts=attempts,
    )


if __name__ == "__main__":
    from app.services.repair.prompt import Prompt

    result = generate(Prompt(system="Reply with exactly the HTML requested and nothing else.",
                             user="Return exactly: <p>ok</p>"))
    print(result)
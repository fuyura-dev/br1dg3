import time
from copy import deepcopy
from dataclasses import dataclass, field

from google import genai

from app.config import settings
from app.services.repair import controls
from app.services.repair.configuration import request_record
from app.services.repair.usage import usage_counts


def create_client(api_key, **kwargs):
    instance = genai.Client(api_key=api_key, **kwargs)
    # google-genai 2.24.0 normalizes HttpRetryOptions(attempts=0) to 1,
    # which Interactions interprets as an extra retry. Disable its actual
    # retry configuration instead; MockTransport tests verify one SDK attempt.
    instance.interactions.sdk_configuration.retry_config = None
    return instance


client = create_client(settings.LLM_API_KEY)


@dataclass
class RequestAttempt:
    number: int
    status: str
    latency_s: float
    raw_usage: dict | None = None
    error: str | None = None


@dataclass
class LLMResult:
    text: str
    ok: bool                 # completed AND non-empty text (a truncated reply is NOT ok)
    status: str | None       # the interaction status, e.g. "completed", "incomplete"
    model: str
    prompt_tokens: int | None       # provider's total_input_tokens
    completion_tokens: int | None   # provider's total_output_tokens; no billing interpretation
    thought_tokens: int | None      # provider's total_thought_tokens
    total_tokens: int | None        # provider total only; never reconstructed from components
    latency_s: float                # last application attempt, including failure
    attempts: int                   # create() invocations; SDK-internal retries now disabled
    raw_usage: dict | None = None   # unmodified usage fields from the final response/error
    attempt_records: list[RequestAttempt] = field(default_factory=list)
    elapsed_s: float | None = None  # whole generation including application retry delays
    request: dict | None = None     # exact model/settings/prompts, timestamp and request hash
    response_model: str | None = None  # only when actually supplied by the provider


class LLMRequestError(RuntimeError):
    """A terminal request failure carrying the usage evidence collected so far."""

    def __init__(self, cause, result):
        super().__init__(f"{type(cause).__name__}: {cause}")
        self.result = result


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
    return code in controls.RETRY_STATUS or type(exc).__name__ in controls.RETRY_ERRORS


def _raw_usage(usage):
    if isinstance(usage, dict):
        return deepcopy(usage)
    if hasattr(usage, "model_dump"):
        return usage.model_dump(mode="json", exclude_unset=True)
    return None


def generate(prompt) -> LLMResult:
    """prompt: anything with .system and .user (the Prompt from prompt.py)."""
    request = {
        "model": settings.LLM_MODEL,
        "system_instruction": prompt.system,
        "input": prompt.user,
        "store": False,                       # stateless: nothing is kept server-side between calls
    }
    if controls.GENERATION_CONFIG:
        request["generation_config"] = deepcopy(controls.GENERATION_CONFIG)

    records = []
    recorded_request = request_record(request)
    response_model = None
    generation_started = time.perf_counter()

    def result(text, status):
        raw_usage = records[-1].raw_usage
        return LLMResult(
            text=text, ok=status == "completed" and bool(text.strip()), status=status,
            model=settings.LLM_MODEL, **usage_counts(raw_usage),
            latency_s=records[-1].latency_s, attempts=len(records),
            raw_usage=raw_usage, attempt_records=records,
            elapsed_s=round(time.perf_counter() - generation_started, 3),
            request=recorded_request, response_model=response_model,
        )

    while True:
        started = time.perf_counter()
        try:
            interaction = client.interactions.create(**request)
            break
        except Exception as exc:
            usage = _get(exc, "usage")
            if usage is None:
                usage = _get(_get(exc, "body"), "usage")
            records.append(RequestAttempt(
                number=len(records) + 1, status="request_error",
                latency_s=round(time.perf_counter() - started, 3), raw_usage=_raw_usage(usage),
                error=f"{type(exc).__name__}: {exc}",
            ))
            if len(records) > controls.MAX_RETRIES or not _is_transient(exc):
                raise LLMRequestError(exc, result("", "request_error")) from exc
            time.sleep(controls.retry_delay(len(records) - 1))
    latency = time.perf_counter() - started

    usage = _get(interaction, "usage")
    model = _get(interaction, "model")
    response_model = model if isinstance(model, str) else None
    text = _text(interaction)
    status = _get(interaction, "status")
    status = str(getattr(status, "value", status)).lower() if status is not None else None
    records.append(RequestAttempt(
        number=len(records) + 1, status=status or "unknown",
        latency_s=round(latency, 3), raw_usage=_raw_usage(usage),
    ))
    completed = result(text, status)

    from app.services.repair.log_streamer import streamer
    streamer.log(
        f"[LLM] Status: {status} | Latency: {round(latency, 2)}s | "
        f"Input: {completed.prompt_tokens} | Output: {completed.completion_tokens} | "
        f"Thought: {completed.thought_tokens} | Total: {completed.total_tokens} tokens (None = unreported)"
    )
    return completed


if __name__ == "__main__":
    from app.services.repair.prompt import Prompt

    result = generate(Prompt(system="Reply with exactly the HTML requested and nothing else.",
                             user="Return exactly: <p>ok</p>"))
    print(result)

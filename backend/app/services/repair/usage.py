"""Provider-reported usage and application-attempt coverage"""

TOKEN_FIELDS = {
    "prompt_tokens": "total_input_tokens",
    "completion_tokens": "total_output_tokens",
    "thought_tokens": "total_thought_tokens",
    "total_tokens": "total_tokens",
}

# Explicit non-completed statuses in saved Interactions responses, plus our
# application exception status. Missing/unrecognized status is not proof of zero.
NONCOMPLETED_STATUSES = frozenset({
    "request_error", "incomplete", "failed", "cancelled", "budget_exceeded",
    "in_progress", "requires_action", "queued",
})


def token_count(value):
    # Missing, malformed and negative values are unknown, not zero.
    return value if type(value) is int and value >= 0 else None


def usage_counts(raw_usage):
    return {name: token_count((raw_usage or {}).get(key)) for name, key in TOKEN_FIELDS.items()}


def generation_attempted(step):
    recorded = getattr(step, "generation_attempted", None)
    if recorded is not None:
        return bool(recorded or getattr(step, "llm", None))
    status = getattr(step, "status", "")
    return bool(getattr(step, "llm", None) or status.startswith("llm_") or status in {
        "applied", "empty_reply", "no_element", "not_html", "invalid_reply",
        "tracking_rejected", "patch_rejected",
    })


def summarize_usage(steps):
    """Complete totals are null if any observed application attempt lacks usage.

    Reported subtotals remain available separately. Current clients disable
    SDK-internal retries; historical records may exclude them. Neither these
    counts nor provider usage prove billed cost.
    Legacy result objects lack attempt records, so earlier retries are unknown.
    """
    reported = dict.fromkeys(TOKEN_FIELDS, 0)
    complete = dict.fromkeys(TOKEN_FIELDS, True)
    api_calls = known_requests = 0
    request_count_complete = True
    for step in steps:
        if not generation_attempted(step):
            continue
        api_calls += 1
        result = getattr(step, "llm", None)
        attempts = token_count(getattr(result, "attempts", None))
        if attempts is None:
            request_count_complete = False
        else:
            known_requests += attempts
        records = getattr(result, "attempt_records", None)
        if records:
            samples = [usage_counts(record.raw_usage) for record in records]
            if attempts != len(records):
                complete = dict.fromkeys(TOKEN_FIELDS, False)
        elif result is not None:
            samples = [{name: token_count(getattr(result, name, None)) for name in TOKEN_FIELDS}]
            if attempts != 1:
                complete = dict.fromkeys(TOKEN_FIELDS, False)
        else:
            samples = [dict.fromkeys(TOKEN_FIELDS)]
        for sample in samples:
            for name, value in sample.items():
                if value is None:
                    complete[name] = False
                else:
                    reported[name] += value
    return {
        "api_calls": api_calls,
        "requests": known_requests if request_count_complete else None,
        "known_requests": known_requests,
        "request_count_complete": request_count_complete,
        "request_count_basis": "application_attempts",
        "reported_usage": reported,
        "usage_complete": complete,
        "total_tokens_source": "provider_reported",
        **{name: reported[name] if complete[name] else None for name in TOKEN_FIELDS},
    }


def summarize_completed_usage(steps):
    """Summarize completed responses, independently of patch acceptance or billing.

    Existing all-attempt usage remains separate. Incomplete attempt histories or
    unknown completion status leave totals unavailable but retain known subtotals.
    """
    known_count = 0
    count_complete = True
    reported = dict.fromkeys(TOKEN_FIELDS, 0)
    complete = dict.fromkeys(TOKEN_FIELDS, True)
    for step in steps:
        if not generation_attempted(step):
            continue
        result = getattr(step, "llm", None)
        attempts = token_count(getattr(result, "attempts", None))
        records = getattr(result, "attempt_records", None)
        if records:
            if attempts != len(records):
                count_complete = False
            samples = [(getattr(record, "status", None), usage_counts(getattr(record, "raw_usage", None)))
                       for record in records]
        elif result is not None:
            # Legacy final-response evidence cannot establish earlier outcomes.
            if attempts != 1:
                count_complete = False
            samples = [(getattr(result, "status", None), {
                name: token_count(getattr(result, name, None)) for name in TOKEN_FIELDS
            })]
        else:
            count_complete = False
            continue

        for status, counts in samples:
            if status == "completed":
                known_count += 1
                for name, value in counts.items():
                    if value is None:
                        complete[name] = False
                    else:
                        reported[name] += value
            elif status not in NONCOMPLETED_STATUSES:
                count_complete = False

    if not count_complete:
        complete = dict.fromkeys(TOKEN_FIELDS, False)
    return {
        "completed_response_count": known_count if count_complete else None,
        "completed_response_usage": {
            "basis": "completed_responses",
            "known_completed_responses": known_count,
            "count_complete": count_complete,
            "reported_usage": reported,
            "usage_complete": complete,
            "total_tokens_source": "provider_reported",
            **{name: reported[name] if complete[name] else None for name in TOKEN_FIELDS},
        },
    }

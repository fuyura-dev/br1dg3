from dataclasses import asdict
from hashlib import sha256
from time import monotonic
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.detection.detect import scan_with_report
from app.services.detection.preprocess import (
    stash_non_essential,
    unstash_non_essential,
)
from app.services.repair.failed_runs import save_failed_run
from app.services.repair.log_streamer import streamer
from app.services.repair.runner import run_baseline, run_sdg
from app.services.validation.evaluator import evaluate_repair

router = APIRouter()

@router.get("/repair/logs")
async def repair_logs():
    return StreamingResponse(streamer.subscribe(), media_type="text/event-stream")

class RepairRequest(BaseModel):
    html: str
    use_sdg: bool = True
    use_cache: bool = Field(
        default=True,
        description="Reuse cached repair responses. Set false to bypass cache reads and writes.",
    )

class RepairResponse(BaseModel):
    fixed_html: str
    candidate_html: str | None = Field(
        default=None, description="Accepted assembled candidate before script/style restoration; null if none.",
    )
    generation: dict[str, Any] | None = None
    configuration: dict[str, Any] | None = None
    issues_before: int
    issues_after: int
    issues_fixed: int           # issues_before - issues_after (can be negative if repair regresses)
    summary: str
    metrics: dict[str, Any] | None = None
    steps: list[dict[str, Any]] | None = None
    scan_reports: dict[str, Any] = Field(default_factory=lambda: {"before": None, "after": None})
    cache_hit: bool = Field(
        default=False,
        description="True when reusing a cached response; metrics describe the original repair run.",
    )


def _count_issues(violations: list[dict]) -> int:
    """Same granularity as ScanResponse.total_issues: one count per violation node, not per rule."""
    return sum(len(v.get("nodes", [])) for v in violations)


def _summarize(request: "RepairRequest", run, issues_before: int, issues_after: int) -> str:
    def available(value):
        return value if value is not None else "unavailable"
    tokens_detail = (
        f"{available(run.total_tokens)} tokens "
        f"[{available(run.prompt_tokens)} input, {available(run.completion_tokens)} output, "
        f"{available(run.thought_tokens)} thought]"
    )
    tail = (f"{issues_before} -> {issues_after} issues ({run.api_calls} generations, "
            f"{available(run.requests)} application attempts, {tokens_detail})")
    if run.fallback_used:
        return f"No accepted repair candidate; fallback HTML returned. {run.failed_steps} failed steps, {run.unmapped} unmapped, {tail}."
    if request.use_sdg:
        applied = sum(1 for s in run.steps if s.status == "applied")
        cascaded = sum(1 for s in run.steps if s.status in {"cascade_skipped", "cascade_resolved"})
        return f"SDG repair ({run.generation_status}): {applied} patched, {cascaded} locally skipped (not individually Axe-verified), {run.failed_steps} failed, {len(run.steps)} total elements, {run.unmapped} unmapped, {tail}."
    step = run.steps[0] if run.steps else None
    return f"Baseline repair: {step.status if step else 'no_violations'}, {tail}."


def _serialize_steps(run) -> list[dict[str, Any]]:
    return [
        {
            "token": s.token,
            "original_node_id": s.original_node_id,
            "node_id": s.node_id,
            "tag": s.tag,
            "rules": s.rules,
            "requested_rules": s.requested_rules,
            "skipped_rules": s.skipped_rules,
            "edit_scope": s.edit_scope,
            "reply_scope": s.reply_scope,
            "reply_html": s.reply_html,
            "status": s.status,
            "repaired_html": s.llm.text.strip() if s.llm and s.llm.text else None,
            "raw_reply": s.llm.text if s.llm is not None else None,
            "candidate_html": s.candidate_html,
            "related_relationships": s.related_relationships,
            "warnings": s.warnings,
            "error": s.error,
            "generation_attempted": s.generation_attempted,
            "llm": asdict(s.llm) if s.llm is not None else None,
        }
        for s in run.steps
    ]


cache: dict[tuple[str, bool], tuple[float, RepairResponse]] = {}
TTL = 300


@router.post("/repair", response_model=RepairResponse)
def repair_html(request: RepairRequest):
    cache_key = None
    if request.use_cache:
        cache_key = (sha256(request.html.encode()).hexdigest(), request.use_sdg)
        cached = cache.get(cache_key)
        if cached is not None:
            stored_at, cached_response = cached
            if monotonic() - stored_at < TTL:
                return cached_response.model_copy(update={"cache_hit": True}, deep=True)
            cache.pop(cache_key, None)

    clean_html, stashed_assets = stash_non_essential(request.html)
    try:
        scan_before = scan_with_report(clean_html)
        violations_before = scan_before.violations
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail=f"Accessibility detection failed: {e!s}",
        )

    issues_before = _count_issues(violations_before)

    if not violations_before:
        return RepairResponse(
            fixed_html=request.html, issues_before=0, issues_after=0, issues_fixed=0,
            summary="No confirmed selected-rule violations detected.",
            steps=[],
            scan_reports={"before": scan_before.report, "after": None},
            generation={"status": "not_needed", "candidate_available": False,
                        "fallback_used": False, "failed_steps": 0, "unmapped": 0},
        )

    run = run_sdg(clean_html, violations_before) if request.use_sdg \
        else run_baseline(clean_html, violations_before)
    if run.configuration is not None:
        run.configuration["api_cache_enabled"] = request.use_cache

    streamer.log("[POST-REPAIR] Repair steps completed. Starting post-repair verification...")
    streamer.log("[POST-REPAIR] Running post-repair Axe accessibility scan on fixed HTML...")

    try:
        scan_after = scan_with_report(run.fixed_html)
        violations_after = scan_after.violations
    except Exception as e:  # noqa: BLE001
        streamer.log(f"[POST-REPAIR] Post-repair detection failed: {e!s}")
        try:
            record_id = save_failed_run(
                original_html=request.html,
                evaluation_original_html=clean_html,
                use_sdg=request.use_sdg,
                violations_before=violations_before,
                run=run,
                error=e,
                scan_report_before=scan_before.report,
            )
        except Exception as storage_error:  # noqa: BLE001 - preserve the original scan error
            streamer.log(f"[POST-REPAIR] Failed-run record could not be saved: {storage_error}")
        else:
            streamer.log(f"[POST-REPAIR] Failed-run record saved: {record_id}")
        raise HTTPException(
            status_code=503,
            detail=f"Post-repair detection failed: {e!s}",
        )

    issues_after = _count_issues(violations_after)
    streamer.log(f"[POST-REPAIR] Axe scan completed: {issues_before} -> {issues_after} issues ({issues_before - issues_after} resolved).")
    streamer.log("[POST-REPAIR] Computing evaluation metrics (Effectiveness, Safety, Structure, Efficiency, Semantic)...")

    metrics_report = evaluate_repair(
        html_original=clean_html,
        html_repaired=run.fixed_html,
        violations_before=violations_before,
        violations_after=violations_after,
        repair_run=run,
        run_detection_if_missing=False,
    )
    streamer.log("[DONE] Evaluation metrics computed successfully. Repair complete!")

    repaired_html = unstash_non_essential(run.fixed_html, stashed_assets)
    metrics = metrics_report.to_dict()
    # Reports are exposed once at the response level. Evaluation received the
    # already selected lists, so it did not generate its own scan reports.
    metrics.pop("scan_reports", None)

    response = RepairResponse(
        fixed_html=repaired_html,
        candidate_html=run.candidate_html,
        generation=run.generation_summary(),
        configuration=run.configuration,
        issues_before=issues_before,
        issues_after=issues_after,
        issues_fixed=issues_before - issues_after,
        summary=_summarize(request, run, issues_before, issues_after),
        metrics=metrics,
        scan_reports={"before": scan_before.report, "after": scan_after.report},
        steps=_serialize_steps(run),
    )
    if cache_key is not None:
        cache[cache_key] = (monotonic(), response.model_copy(deep=True))
    return response

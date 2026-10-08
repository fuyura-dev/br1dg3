from hashlib import sha256
from time import time
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.detection.detect import detect
from app.services.detection.preprocess import (
    stash_non_essential,
    unstash_non_essential,
)
from app.services.repair.runner import run_baseline, run_sdg
from app.services.validation.evaluator import evaluate_repair
from app.services.repair.log_streamer import streamer

router = APIRouter()

@router.get("/repair/logs")
async def repair_logs():
    return StreamingResponse(streamer.subscribe(), media_type="text/event-stream")

class RepairRequest(BaseModel):
    html: str
    use_sdg: bool = True

class RepairResponse(BaseModel):
    fixed_html: str
    issues_before: int
    issues_after: int
    issues_fixed: int           # issues_before - issues_after (can be negative if repair regresses)
    summary: str
    metrics: dict[str, Any] | None = None
    steps: list[dict[str, Any]] | None = None


def _count_issues(violations: list[dict]) -> int:
    """Same granularity as ScanResponse.total_issues: one count per violation node, not per rule."""
    return sum(len(v.get("nodes", [])) for v in violations)


def _summarize(request: "RepairRequest", run, issues_before: int, issues_after: int) -> str:
    tokens_detail = (
        f"{run.total_tokens} tokens "
        f"[{run.prompt_tokens} input, {run.completion_tokens} output, {run.thought_tokens} thought]"
    )
    tail = f"{issues_before} -> {issues_after} issues ({run.api_calls} API calls, {tokens_detail})"
    if request.use_sdg:
        applied = sum(1 for s in run.steps if s.status == "applied")
        cascaded = sum(1 for s in run.steps if s.status == "cascade_resolved")
        return f"SDG repair: {applied} patched, {cascaded} cascaded, {len(run.steps)} total elements, {run.unmapped} unmapped, {tail}."
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
            "status": s.status,
            "repaired_html": s.llm.text.strip() if s.llm and s.llm.text else None,
            "related_relationships": s.related_relationships,
            "warnings": s.warnings,
            "error": s.error,
        }
        for s in run.steps
    ]


cache = {}
TTL = 300

@router.post("/repair", response_model=RepairResponse)
def repair_html(request: RepairRequest):
    html_hash = sha256(request.html.encode()).hexdigest() # TODO: include if use sdg in hash key

    if html_hash in cache and time() - cache[html_hash]["time"] < TTL:
        return cache[html_hash]["response"]
    
    clean_html, stashed_assets = stash_non_essential(request.html)
    try:
        violations_before = detect(clean_html)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail=f"Accessibility detection failed: {e!s}",
        )

    issues_before = _count_issues(violations_before)

    if not violations_before:
        return RepairResponse(
            fixed_html=request.html, issues_before=0, issues_after=0, issues_fixed=0,
            summary="No accessibility issues detected.",
            steps=[],
        )

    run = run_sdg(clean_html, violations_before) if request.use_sdg \
        else run_baseline(clean_html, violations_before)

    streamer.log("[POST-REPAIR] Repair steps completed. Starting post-repair verification...")
    streamer.log("[POST-REPAIR] Running post-repair Axe accessibility scan on fixed HTML...")

    try:
        violations_after = detect(run.fixed_html)
    except Exception as e:  # noqa: BLE001
        streamer.log(f"[POST-REPAIR] Post-repair detection failed: {e!s}")
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

    cache[html_hash] = {
        "response": RepairResponse(
            fixed_html=repaired_html,
            issues_before=issues_before,
            issues_after=issues_after,
            issues_fixed=issues_before - issues_after,
            summary=_summarize(request, run, issues_before, issues_after),
            metrics=metrics_report.to_dict(),
            steps=_serialize_steps(run),
        ),
        "time": time()
    }
    return cache[html_hash]["response"]



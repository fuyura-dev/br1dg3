from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.detection.detect import detect
from app.services.repair.runner import run_baseline, run_sdg

router = APIRouter()

class RepairRequest(BaseModel):
    html: str
    use_sdg: bool = True

class RepairResponse(BaseModel):
    fixed_html: str
    issues_before: int
    issues_after: int
    issues_fixed: int           # issues_before - issues_after (can be negative if repair regresses)
    summary: str


def _count_issues(violations: list[dict]) -> int:
    """Same granularity as ScanResponse.total_issues: one count per violation node, not per rule."""
    return sum(len(v.get("nodes", [])) for v in violations)


def _summarize(request: "RepairRequest", run, issues_before: int, issues_after: int) -> str:
    tail = f"{issues_before} -> {issues_after} issues ({run.api_calls} API calls, {run.total_tokens} tokens)"
    if request.use_sdg:
        applied = sum(1 for s in run.steps if s.status == "applied")
        return f"SDG repair: {applied}/{len(run.steps)} elements patched, {run.unmapped} unmapped, {tail}."
    step = run.steps[0] if run.steps else None
    return f"Baseline repair: {step.status if step else 'no_violations'}, {tail}."


@router.post("/repair", response_model=RepairResponse)
def repair_html(request: RepairRequest):
    try:
        violations_before = detect(request.html)
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Accessibility detection failed: {str(e)}",
        )

    issues_before = _count_issues(violations_before)

    if not violations_before:
        return RepairResponse(
            fixed_html=request.html, issues_before=0, issues_after=0, issues_fixed=0,
            summary="No accessibility issues detected.",
        )

    run = run_sdg(request.html, violations_before) if request.use_sdg \
        else run_baseline(request.html, violations_before)

    try:
        violations_after = detect(run.fixed_html)
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Post-repair detection failed: {str(e)}",
        )

    issues_after = _count_issues(violations_after)

    return RepairResponse(
        fixed_html=run.fixed_html,
        issues_before=issues_before,
        issues_after=issues_after,
        issues_fixed=issues_before - issues_after,
        summary=_summarize(request, run, issues_before, issues_after),
    )



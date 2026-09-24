from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.validation.evaluator import evaluate_repair

router = APIRouter()


class EvaluateRequest(BaseModel):
    html_original: str
    html_repaired: str
    violations_before: list[dict] | None = None
    violations_after: list[dict] | None = None
    efficiency_data: dict[str, Any] | None = None
    structure_threshold: float = 0.85
    run_detection_if_missing: bool = True


class EvaluateResponse(BaseModel):
    effectiveness: dict[str, Any]
    safety: dict[str, Any]
    structure: dict[str, Any]
    efficiency: dict[str, Any]
    semantic: dict[str, Any]


@router.post("/evaluate", response_model=EvaluateResponse)
def evaluate_document_repair(request: EvaluateRequest):
    report = evaluate_repair(
        html_original=request.html_original,
        html_repaired=request.html_repaired,
        violations_before=request.violations_before,
        violations_after=request.violations_after,
        efficiency_data=request.efficiency_data,
        structure_threshold=request.structure_threshold,
        run_detection_if_missing=request.run_detection_if_missing,
    )
    return EvaluateResponse(**report.to_dict())

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.detection.detect import DetectionError
from app.services.validation.evaluator import MissingInitialScanError, evaluate_repair

router = APIRouter()


class EvaluateRequest(BaseModel):
    html_original: str
    html_repaired: str
    violations_before: list[dict] | None = None
    violations_after: list[dict] | None = None
    efficiency_data: dict[str, Any] | None = None
    structure_threshold: float = 0.85
    run_detection_if_missing: bool = True
    fallback_used: bool = Field(
        default=False,
        description="True only when generation produced no accepted candidate and html_repaired is fallback output.",
    )


class EvaluateResponse(BaseModel):
    effectiveness: dict[str, Any]
    safety: dict[str, Any]
    structure: dict[str, Any]
    efficiency: dict[str, Any]
    semantic: dict[str, Any]
    evaluation: dict[str, Any]


@router.post("/evaluate", response_model=EvaluateResponse)
def evaluate_document_repair(request: EvaluateRequest):
    try:
        report = evaluate_repair(
            html_original=request.html_original,
            html_repaired=request.html_repaired,
            violations_before=request.violations_before,
            violations_after=request.violations_after,
            efficiency_data=request.efficiency_data,
            structure_threshold=request.structure_threshold,
            run_detection_if_missing=request.run_detection_if_missing,
            fallback_used=request.fallback_used,
        )
    except MissingInitialScanError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DetectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return EvaluateResponse(**report.to_dict())

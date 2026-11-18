from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.detection.detect import scan_with_report

router = APIRouter()

# https://github.com/dequelabs/axe-core/blob/develop/doc/API.md#results-object

class Issue(BaseModel):
    id: str                     # violations.id
    impact: str | None = None                 # violations.nodes.impact
    tags: list[str]= []         # violations.tags
    description: str            # violations.description
    html_target: str            # violations.nodes.html
    help: str                   # violations.help
    help_url: str               # violations.helpUrl
    target: list[str] = []                 # node.target


class ScanRequest(BaseModel):
    html: str

class ScanResponse(BaseModel):
    total_issues: int
    issues: list[Issue]
    scan_report: dict[str, Any]


@router.post("/scan", response_model=ScanResponse)
def scan_html(request: ScanRequest):
    print(f"\n[SCAN] Received scan request from extension ({len(request.html)} characters)")
    try:
        scan = scan_with_report(request.html)
        violations = scan.violations
    except Exception as e:  # noqa: BLE001 - browser and Axe failures retain HTTP 503
        print(f"[SCAN] Detection failed: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Accessibility detection failed: {e!s}",
        )

    issues: list[Issue] = []

    for v in violations:
        for node in v.get("nodes", []):
            issues.append(
                Issue(
                    id=v.get("id", ""),
                    impact=node.get("impact"),
                    tags=v.get("tags", []),
                    description=v.get("description", ""),
                    html_target=node.get("html", ""),
                    help=v.get("help", ""),
                    help_url=v.get("helpUrl", ""),
                    target=node.get("target", []),
                )
            )

    print(f"[SCAN] Detection completed: Found {len(issues)} violations across {len(violations)} rules.")
    return ScanResponse(total_issues=len(issues), issues=issues, scan_report=scan.report)



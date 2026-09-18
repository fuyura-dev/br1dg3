from fastapi import APIRouter
from pydantic import BaseModel

from app.services.detection.detect import detect

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


@router.post("/scan", response_model=ScanResponse)
async def scan_html(request: ScanRequest):
    violations = detect(request.html)

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

    return ScanResponse(total_issues=len(issues), issues=issues)


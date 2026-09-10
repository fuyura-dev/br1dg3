from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

router = APIRouter()

# https://github.com/dequelabs/axe-core/blob/develop/doc/API.md#results-object

class Issue(BaseModel):
    id: str                     # violations.id
    impact: str                 # violations.nodes.impact
    tags: List[str]= []         # violations.tags
    description: str            # violations.description
    html_target: str            # violations.nodes.html
    help: str                   # violations.help
    help_url: str               # violations.helpUrl
    target: str                 # node.target


class ScanRequest(BaseModel):
    html: str

class ScanResponse(BaseModel):
    total_issues: int
    issues: List[Issue]


@router.post("/scan", response_model=ScanResponse)
async def scan_html(request: ScanRequest):

    sample = Issue(
        id="image-alt",
        impact="critical",
        tags=["wcag2a", "wcag111"],
        description="Ensures <img> elements have alternate text",
        help="Images must have alternate text",
        help_url="https://dequeuniversity.com/rules/axe/4.10/image-alt",
        html_target="<img src='logo.png'>",
        target="header > img.logo"
    )

    return ScanResponse(total_issues=1, issues=[sample])
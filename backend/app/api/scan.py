from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

router = APIRouter()

class Issue(BaseModel):
    id: str
    description: str

class ScanRequest(BaseModel):
    html: str

class ScanResponse(BaseModel):
    total_issues: int
    issues: List[Issue]


@router.post("/scan", response_model=ScanResponse)
async def scan_html(request: ScanRequest):

    sample = Issue(
        id="test",
        description="test desc"
    )

    return ScanResponse(total_issues=1, issues=[sample])
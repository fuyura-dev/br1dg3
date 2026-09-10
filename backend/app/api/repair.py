from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class RepairRequest(BaseModel):
    html: str
    use_sdg: bool = True

class RepairResponse(BaseModel):
    fixed_html: str
    issues_fixed: int
    summary: str

@router.post("/repair", response_model=RepairResponse)
async def repair_html(request: RepairRequest):

    return RepairResponse(
        fixed_html="test fixed html",
        issues_fixed=1,
        summary="test summary"
    )


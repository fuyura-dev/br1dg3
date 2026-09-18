from fastapi import APIRouter
from pydantic import BaseModel

from app.services.detection.detect import detect
from app.services.sdg.builder import SDGBuilder

router = APIRouter()

class NodeIssue(BaseModel):
    id: str
    impact: str | None = None
    description: str | None = None
    help: str | None = None
    help_url: str | None = None
    html: str | None = None

class GraphNode(BaseModel):
    id: str                     # node-id (generated internally)
    tag: str
    label: str
    has_issue: bool = False
    issues: list[NodeIssue] = []

class GraphLink(BaseModel):
    source: str
    target: str
    relation: str               # SDG Relationship

class GraphRequest(BaseModel):
    html: str

class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    links: list[GraphLink]


@router.post("/graph", response_model=GraphResponse)
async def get_dependency_graph(request: GraphRequest):
    violations = detect(request.html)

    builder = SDGBuilder(request.html, violations=violations)
    graph_data = builder.to_dict()


    return GraphResponse(nodes=graph_data["nodes"], links=graph_data["edges"])


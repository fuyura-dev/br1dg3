from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.detection.detect import detect
from app.services.repair.context import ContextExtractor, context_to_dict
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
    contexts: dict[str, Any] = {}


@router.post("/graph", response_model=GraphResponse)
def get_dependency_graph(request: GraphRequest):
    try:
        violations = detect(request.html)
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Accessibility detection failed: {str(e)}",
        )

    builder = SDGBuilder(request.html, violations=violations)
    graph_data = builder.to_dict()
    extractor = ContextExtractor.from_builder(builder)

    contexts: dict[str, Any] = {}
    for node_id, data in builder.graph.nodes(data=True):
        if data.get("has_issue"):
            contexts[node_id] = context_to_dict(extractor.extract(node_id))

    return GraphResponse(
        nodes=graph_data["nodes"],
        links=graph_data["edges"],
        contexts=contexts,
    )



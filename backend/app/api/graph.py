from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

router = APIRouter()

class GraphNode(BaseModel):
    id: str
    tag: str
    has_issue: bool = False

class GraphLink(BaseModel):
    source: str
    target: str
    relation: str

class GraphRequest(BaseModel):
    html: str

class GraphResponse(BaseModel):
    nodes: List[GraphNode]
    links: List[GraphLink]


@router.post("/graph", response_model=GraphResponse)
async def get_dependency_graph(request: GraphRequest):

    sample_nodes = [

    ]
    sample_links = [

    ]

    return GraphResponse(nodes=sample_nodes, links=sample_links)


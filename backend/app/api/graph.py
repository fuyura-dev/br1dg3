from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class GraphNode(BaseModel):
    id: str                     # node-id (generated internally)
    tag: str
    label: str
    has_issue: bool = False

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

    sample_nodes = [
        GraphNode(id="n1", tag="form", label="<form id='login-form'>", has_issue=False),
        GraphNode(id="n2", tag="label", label="<label for='email'>", has_issue=False),
        GraphNode(id="n3", tag="input", label="<input id='email'>", has_issue=True),
        GraphNode(id="n4", tag="button", label="<button type='submit'>", has_issue=False),
    ]
    sample_links = [
        GraphLink(source="n1", target="n3", relation="parent_child"),
        GraphLink(source="n1", target="n4", relation="parent_child"),
        GraphLink(source="n2", target="n3", relation="label_input"),
    ]

    return GraphResponse(nodes=sample_nodes, links=sample_links)


# BR1DG3

> [!NOTE]
> For the updated request and response schemas, refer to the interactive API documentation when the backend is running:
> - **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
> - **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

## Setup guide

### 1. Set Up and Run the Backend
Follow the instructions in the [Backend README](./backend/README.md):


## TODO Backend


### 1. Detection
- [x] Axe-core
- [x] Connect to SDG nodes (`has_issue = True`)

### 2. SDG
- [x] Graph builder
- [x] 8 relationships

### 3. LLM Repair
- [ ] context extraction
- [ ] repair order
- [ ] prompt construction
- [ ] baseline repair (if needed in tool defense)

### 4. Validation & Evaluation (original document vs repaired wit SDG only)
- [ ] Repair Effectiveness
- [ ] Repair Safety
- [ ] Structural Preservation
- [ ] Repair Efficiency
- [ ] Semantic Dependency Preservation

### 5. APIs
- [x] API Skeleton
- [x] connect `/api/scan`
- [x] connect `/api/graph`
- [ ] connect `/api/repair`
- [ ] API for validation and evaluation details

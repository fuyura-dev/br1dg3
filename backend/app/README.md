# 


## API
### [API README](./api/README.md)


## Services

### 1. Detection (`services/detection/`)
* runs axe-core
* extract violations

### 2. LLM Repair (`services/repair/`)
* handles prompt construction

### 3. SDG Engine (`services/sdg/`)

* **`builder.py` (`SDGBuilder`)** graph builder, calls the extractors
* **`extractors/`** 8 extractors for relationships

### 4. Validation (`services/validation/`)
* evaluation of the repaired HTML using the 5 metrics
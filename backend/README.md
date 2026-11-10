# BR1DG3 Backend

## Docs

* [**App**](./app/README.md) - Overview of structure
* [**API**](./app/api/README.md) - Request and response schemas
* [**Structural preservation**](./app/services/validation/README.md) - Unpruned TED and optional legacy comparison

## Setup
```
cd backend

python3 -m venv .venv
```


## Running

### Linux
```
source .venv/bin/activate
```

### Windows
```
source .venv/Scripts/activate.bat
```

### Install dependencies
```
pip install -r requirements.txt
```

### Run
```
uvicorn app.main:app
```
# BR1DG3 Backend

## Docs

* [**App**](./app/README.md) - Overview of structure
* [**API**](./app/api/README.md) - Request and response schemas

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

## API Endpoints
* Backend API: `http://localhost:8000`

More Details: [API README](./app/api/README.md)

| Method | Endpoint |
| :--- | :--- |
| **POST** | `/api/scan` |
| **POST** | `/api/repair` |
| **POST** | `/api/graph` |
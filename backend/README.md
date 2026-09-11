# BR1DG3 Backend

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
* Interactive API Docs: `http://localhost:8000/docs`

More Details: [API README](./app/api/README.md)

| Method | Endpoint |
| :--- | :--- |
| **POST** | `/api/scan` |
| **POST** | `/api/repair` |
| **POST** | `/api/graph` |
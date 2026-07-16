# HaloITSM Value-Gap Lead Agent

Evidence-backed lead intelligence MVP that identifies organisations which appear to use ServiceNow mainly for basic ITSM and may be suitable for a HaloITSM value assessment.

## Quick Start

### 1. Prerequisites

- Python 3.12+
- Docker Desktop (for PostgreSQL)
- An OpenAI API key

### 2. Create and activate virtual environment

```powershell
cd halo-lead-agent
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
pip install -e ".[dev]"
```

### 4. Configure environment

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set `OPENAI_API_KEY`.

### 5. Start PostgreSQL

```powershell
docker compose up -d
```

### 6. Run database migrations

```powershell
alembic upgrade head
```

### 7. Start the API server

```powershell
fastapi dev app/main.py
```

### 8. Open API documentation

Navigate to: http://127.0.0.1:8000/docs

---

## API Overview

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| POST | /organisations | Create an organisation |
| GET | /organisations | List all organisations |
| GET | /organisations/{id} | Get one organisation |
| POST | /research/organisations/{id} | Start a research run |
| GET | /research/runs/{run_id} | Get run status and assessment |
| PATCH | /reviews/assessments/{assessment_id} | Accept / reject / request more research |

---

## Running Tests

```powershell
pytest -v
```

---

## Security Notes

- Never commit `.env` to version control.
- The application uses public web information only.
- Human review is required before any outreach action.

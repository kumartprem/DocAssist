# DocAssist — Document Collection Assistant

A simple tool for lawyers to collect documents from clients. Create a case, define what documents you need, share a link with your client, and track everything automatically.

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the server

```bash
uvicorn main:app --reload
```

### 3. Open in browser

- **Lawyer Dashboard:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs

## How It Works

1. **Lawyer** opens the dashboard and creates a new case with a checklist of required documents
2. **System** generates a unique client portal link
3. **Lawyer** shares the link with the client (copy from dashboard)
4. **Client** opens the link and uploads documents one by one
5. **Lawyer** sees real-time progress on the dashboard

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/cases` | Create a new case |
| GET | `/api/cases` | List all cases |
| GET | `/api/cases/{id}` | Get case details |
| DELETE | `/api/cases/{id}` | Delete a case |
| POST | `/api/cases/{id}/checklist` | Add checklist item |
| DELETE | `/api/checklist/{id}` | Remove checklist item |
| GET | `/api/client/{token}` | Client: view case |
| POST | `/api/client/{token}/upload/{item_id}` | Client: upload document |

## Tech Stack

- **Backend:** FastAPI + SQLAlchemy + SQLite
- **Frontend:** Vanilla HTML/CSS/JS (Jinja2 templates)
- **Storage:** Local filesystem (`uploads/` directory)

# DocAssist — Architecture & Deployment Guide

PROJECT TEAM
Ankit Bisht   •   Aruna Kunche   •   Prem Kumar Thulasi Kumar   •   Wabun Nembang Subba

**Document Collection Assistant for Lawyers**

This document describes the complete technical architecture of DocAssist — system
design, data model, call flows, front-end and back-end internals — and provides a
detailed, step-by-step guide for deploying the solution to **Google Cloud Platform (GCP)**.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Component Architecture](#3-component-architecture)
4. [Data Model](#4-data-model)
5. [API Surface](#5-api-surface)
6. [Call Flows](#6-call-flows)
7. [Backend Details](#7-backend-details)
8. [Frontend Details](#8-frontend-details)
9. [Security Model & Considerations](#9-security-model--considerations)
10. [Deploying to Google Cloud Platform](#10-deploying-to-google-cloud-platform)
11. [Appendix: Configuration & Environment Variables](#11-appendix-configuration--environment-variables)

---

## 1. System Overview

DocAssist is a lightweight web application that lets a **lawyer** define a checklist of
required documents for a case, share a single secure link with a **client**, and track
document collection in real time as the client uploads files — with no client account or
login required.

| Attribute            | Value                                                        |
|----------------------|--------------------------------------------------------------|
| Architectural style  | Monolithic web app (server-rendered shells + JSON REST API)  |
| Backend framework    | FastAPI (Python, ASGI)                                        |
| Persistence          | SQLAlchemy 2.0 ORM over SQLite (file-based)                   |
| File storage         | Local filesystem (`uploads/<case_id>/`)                      |
| Frontend             | Two Jinja2-served HTML pages driven by vanilla JavaScript    |
| Runtime server       | Uvicorn (ASGI)                                               |
| Auth model           | None for lawyers; opaque per-case access token for clients   |

The application has **two distinct user surfaces** served from the same backend:

- **Lawyer Dashboard** (`/`) — manage cases and checklists, view progress, copy portal links.
- **Client Portal** (`/portal/{token}`) — view the requested checklist and upload files.

---

## 2. High-Level Architecture

```
                         ┌──────────────────────────────────────────────┐
                         │                   Browser                     │
                         │                                               │
   Lawyer ──────────────▶  Dashboard SPA  (/)        Client Portal SPA   ◀──────────── Client
                         │  templates/dashboard.html   templates/portal.html            │
                         └───────────────┬───────────────────┬──────────┘
                                         │  fetch() JSON / multipart        │
                                         ▼                                  ▼
                         ┌──────────────────────────────────────────────┐
                         │              FastAPI Application               │
                         │                  (main.py)                     │
                         │                                                │
                         │  • Page routes  (HTMLResponse via Jinja2)      │
                         │  • Case API     (/api/cases…)                  │
                         │  • Checklist API(/api/.../checklist…)          │
                         │  • Client API   (/api/client/{token}…)         │
                         │                                                │
                         │  Pydantic schemas  ◀── request/response models │
                         └───────┬───────────────────────────┬───────────┘
                                 │ SQLAlchemy ORM             │ file I/O
                                 ▼                            ▼
                     ┌───────────────────────┐   ┌──────────────────────────┐
                     │  SQLite  (docassist.db)│   │  Filesystem  uploads/    │
                     │  cases                 │   │   └── <case_id>/         │
                     │  checklist_items       │   │        └── <item_id>_*   │
                     └───────────────────────┘   └──────────────────────────┘
```

**Key points:**

- The HTML pages are **thin shells**; all dynamic data is fetched from the JSON API and
  rendered client-side. This keeps the backend a clean REST service.
- **Two persistence channels:** structured metadata in SQLite, binary document content on
  the filesystem. The DB stores a *path reference* to each uploaded file, not the bytes.
- Everything runs in a **single process** today — simple to operate, but a deliberate MVP
  choice with clear scaling boundaries (see [§10](#10-deploying-to-google-cloud-platform)).

---

## 3. Component Architecture

| File                         | Layer            | Responsibility                                              |
|------------------------------|------------------|-------------------------------------------------------------|
| `main.py`                    | Application      | FastAPI app, all routes (pages + API), upload handling, app bootstrap (`Base.metadata.create_all`) |
| `database.py`                | Persistence      | SQLAlchemy `engine`, `SessionLocal`, declarative `Base`, `get_db()` dependency |
| `models.py`                  | Domain / ORM     | `Case` and `ChecklistItem` ORM entities, token generator    |
| `schemas.py`                 | Contract         | Pydantic request/response models (validation + serialization) |
| `templates/dashboard.html`   | Presentation     | Lawyer single-page app (list + detail views, modals)        |
| `templates/portal.html`      | Presentation     | Client upload single-page app                               |
| `uploads/`                   | Storage          | Uploaded files, namespaced per case                         |
| `docassist.db`               | Storage          | SQLite database file                                        |
| `requirements.txt`           | Build            | `fastapi`, `uvicorn`, `sqlalchemy`, `python-multipart`, `jinja2`, `aiofiles` |

### Layering

```
Presentation (HTML/JS)  →  API routes (FastAPI)  →  Schemas (Pydantic)
                                     │
                                     ▼
                         Domain models (SQLAlchemy)  →  Engine/Session (database.py)
                                     │                              │
                                     ▼                              ▼
                              Filesystem (uploads/)            SQLite (docassist.db)
```

The separation of **routes / schemas / models / persistence** is what allows the API to
evolve (e.g. swap SQLite for PostgreSQL) without touching the front end, since the JSON
contract is defined by the Pydantic schemas.

---

## 4. Data Model

Defined in [models.py](models.py). Two tables in a **one-to-many** relationship
(`Case` 1 ── N `ChecklistItem`).

### Entity-Relationship Diagram

```
┌─────────────────────────────┐         ┌──────────────────────────────────┐
│            cases            │         │          checklist_items          │
├─────────────────────────────┤         ├──────────────────────────────────┤
│ id            INTEGER  PK   │1       N│ id                 INTEGER  PK    │
│ title         VARCHAR(200)  │─────────│ case_id            INTEGER  FK ───┼──▶ cases.id
│ client_name   VARCHAR(200)  │         │ name               VARCHAR(200)   │
│ client_email  VARCHAR(200)  │         │ description        TEXT (null)    │
│ access_token  VARCHAR(16) U │         │ is_received        BOOLEAN        │
│ created_at    DATETIME      │         │ uploaded_file_path VARCHAR(500)   │
└─────────────────────────────┘         │ uploaded_at        DATETIME (null)│
                                        └──────────────────────────────────┘
   U = unique + indexed                  cascade: all, delete-orphan
```

### `cases`

| Column         | Type         | Constraints / Default                  | Notes                                   |
|----------------|--------------|----------------------------------------|-----------------------------------------|
| `id`           | INTEGER      | PK, indexed                            | Auto-increment                          |
| `title`        | VARCHAR(200) | not null                               | e.g. "Personal Injury — John Doe"       |
| `client_name`  | VARCHAR(200) | not null                               |                                         |
| `client_email` | VARCHAR(200) | not null                               |                                         |
| `access_token` | VARCHAR(16)  | unique, indexed, default `generate_token` | `uuid4().hex[:16]` — drives the portal |
| `created_at`   | DATETIME     | default `utcnow`                       | Stored in UTC                           |

### `checklist_items`

| Column               | Type         | Constraints / Default     | Notes                                       |
|----------------------|--------------|---------------------------|---------------------------------------------|
| `id`                 | INTEGER      | PK, indexed               | Auto-increment                              |
| `case_id`            | INTEGER      | FK → `cases.id`           | Owning case                                 |
| `name`               | VARCHAR(200) | not null                  | e.g. "Government ID"                        |
| `description`        | TEXT         | nullable                  | Optional client guidance                    |
| `is_received`        | BOOLEAN      | default `False`           | Flips to `True` on upload                   |
| `uploaded_file_path` | VARCHAR(500) | nullable                  | Server path of stored file                  |
| `uploaded_at`        | DATETIME     | nullable                  | Upload timestamp (UTC)                      |

**Relationship & integrity rules:**

- `Case.checklist_items` is configured with `cascade="all, delete-orphan"` — deleting a
  case removes its checklist items (and their DB rows) automatically.
- The `access_token` is the **only** identifier exposed to clients; the numeric `case_id`
  is never shared in portal URLs.
- Progress for a case is derived, not stored: `received = count(items where is_received)`
  over `total = count(items)`.

---

## 5. API Surface

All routes are defined in [main.py](main.py). Request/response shapes come from
[schemas.py](schemas.py).

### Pages (server-rendered shells)

| Method | Path                | Response  | Purpose                          |
|--------|---------------------|-----------|----------------------------------|
| GET    | `/`                 | HTML      | Lawyer dashboard                 |
| GET    | `/portal/{token}`   | HTML      | Client upload portal (validates token, 404 if invalid) |

### Case API (lawyer)

| Method | Path                    | Body (schema)   | Returns          |
|--------|-------------------------|-----------------|------------------|
| POST   | `/api/cases`            | `CaseCreate`    | `CaseOut`        |
| GET    | `/api/cases`            | —               | `[CaseSummary]`  |
| GET    | `/api/cases/{case_id}`  | —               | `CaseOut`        |
| DELETE | `/api/cases/{case_id}`  | —               | `{ok: true}`     |

### Checklist API (lawyer)

| Method | Path                              | Body (schema)         | Returns             |
|--------|-----------------------------------|-----------------------|---------------------|
| POST   | `/api/cases/{case_id}/checklist`  | `ChecklistItemCreate` | `ChecklistItemOut`  |
| DELETE | `/api/checklist/{item_id}`        | —                     | `{ok: true}`        |

### Client API (token-scoped, no auth)

| Method | Path                                       | Body            | Returns             |
|--------|--------------------------------------------|-----------------|---------------------|
| GET    | `/api/client/{token}`                      | —               | `CaseOut`           |
| POST   | `/api/client/{token}/upload/{item_id}`     | multipart file  | `ChecklistItemOut`  |

### Schema summary

- **`CaseCreate`** → `title`, `client_name`, `client_email`, `checklist_items: list[str]`
- **`CaseOut`** → full case incl. `access_token` and nested `checklist_items`
- **`CaseSummary`** → list-view projection incl. derived `total_items` / `received_items`
- **`ChecklistItemCreate`** → `name`, optional `description`
- **`ChecklistItemOut`** → `id`, `name`, `description`, `is_received`, `uploaded_at`

> Note: `CaseSummary` deliberately **omits** `access_token`, so the list endpoint never
> leaks portal links; the token is only returned by the single-case `CaseOut`.

---

## 6. Call Flows

### 6.1 Create a case

```
Lawyer (dashboard.html)        FastAPI (main.py)            SQLite
        │ POST /api/cases            │                        │
        │  {title, client_name,      │                        │
        │   client_email,            │                        │
        │   checklist_items[]}       │                        │
        ├───────────────────────────▶│                        │
        │                            │ new Case(...)          │
        │                            │ db.flush() → case.id   │
        │                            │ for each item: add     │
        │                            │   ChecklistItem        │
        │                            │ db.commit()            │
        │                            ├───────────────────────▶│
        │       200 CaseOut          │                        │
        │◀───────────────────────────┤                        │
        │ reload list (GET /api/cases)                        │
```

The `access_token` is generated automatically by the model default during insert.

### 6.2 Share link & client opens portal

```
Lawyer copies portal link:  {origin}/portal/{access_token}
        │
        ▼ (client opens link)
Client browser → GET /portal/{token} → main.py validates token (404 if invalid)
        → returns portal.html shell with {token} injected
        → portal.html calls GET /api/client/{token} → CaseOut (checklist + status)
        → renders checklist with per-item upload buttons
```

### 6.3 Client uploads a document

```
Client (portal.html)            FastAPI (main.py)              SQLite / Filesystem
   │ POST /api/client/{token}/        │                            │
   │   upload/{item_id}               │                            │
   │   (multipart: file)              │                            │
   ├─────────────────────────────────▶│                            │
   │                                  │ find Case by token (404?)  │
   │                                  │ find item by id+case (404?)│
   │                                  │ mkdir uploads/<case_id>/   │
   │                                  │ write <item_id>_<filename> │──▶ filesystem
   │                                  │ item.is_received = True     │
   │                                  │ item.uploaded_file_path=…   │
   │                                  │ item.uploaded_at = utcnow   │
   │                                  │ db.commit()                 │──▶ SQLite
   │      200 ChecklistItemOut        │                            │
   │◀─────────────────────────────────┤                            │
   │ reloadCase() → progress bar advances                          │
```

### 6.4 Lawyer tracks progress

```
dashboard.html → GET /api/cases → [CaseSummary]
   each summary carries total_items & received_items (computed server-side)
   → badge shows received/total or "Complete"; progress bar width = received/total
```

---

## 7. Backend Details

### 7.1 Application bootstrap (`main.py`)

- On import, `Base.metadata.create_all(bind=engine)` creates tables if they don't exist
  (no migration tool — simple create-on-start).
- `UPLOAD_DIR = Path("uploads")` is created at startup (`mkdir(exist_ok=True)`).
- `Jinja2Templates(directory="templates")` renders the two HTML shells.
- The app title is set for the auto-generated OpenAPI docs at `/docs`.

### 7.2 Database session management (`database.py`)

- Engine: `create_engine("sqlite:///./docassist.db", connect_args={"check_same_thread": False})`.
  `check_same_thread=False` is required because FastAPI may use the connection across
  threads.
- `SessionLocal` is a configured `sessionmaker` (no autocommit, no autoflush).
- `get_db()` is a FastAPI dependency that yields a session and guarantees `close()` in a
  `finally` block — one session per request.

### 7.3 Domain models (`models.py`)

- SQLAlchemy 2.0 **typed** style (`Mapped[...]`, `mapped_column(...)`).
- `generate_token()` returns `uuid4().hex[:16]` — a 16-char opaque token used as the
  default for `Case.access_token`.
- Timestamps default to timezone-aware UTC (`datetime.now(timezone.utc)`).

### 7.4 Validation & serialization (`schemas.py`)

- Pydantic models with `model_config = {"from_attributes": True}` so ORM objects serialize
  directly into responses.
- The API contract is enforced at the boundary: malformed requests are rejected by FastAPI
  with `422` before any handler logic runs.

### 7.5 Upload handler specifics

- Declared `async` and reads the file with `await file.read()` (full content into memory),
  then writes bytes to disk.
- Stored filename is `f"{item_id}_{file.filename}"` under `uploads/<case_id>/`.
- Item lookup is **scoped to the case** (`item_id` AND `case_id`) to prevent cross-case
  manipulation via a valid token.

---

## 8. Frontend Details

Both pages are **single-file SPAs**: HTML + embedded CSS + embedded vanilla JS, with no
build step and no framework.

### 8.1 Lawyer Dashboard (`templates/dashboard.html`)

- **Two views toggled in JS:** a *list view* (`#list-view`) and a *detail view*
  (`#detail-view`).
- **List view** (`loadCases()`): fetches `/api/cases`, renders a card per case with a
  progress badge (`received/total` or "Complete") and a green progress bar.
- **Detail view** (`showDetail(id)`): fetches `/api/cases/{id}`, shows the copyable portal
  link (`{origin}/portal/{access_token}`), the checklist with per-item status, and controls
  to add/remove items and delete the case.
- **Modals:** "Create New Case" (collects title/name/email + a client-side checklist array)
  and "Add Checklist Item".
- **Helpers:** `esc()` escapes user content to prevent HTML injection in the rendered DOM.

### 8.2 Client Portal (`templates/portal.html`)

- Receives the `{{ token }}` injected by Jinja2 and builds `API = /api/client/{token}`.
- `loadCase()` fetches the case; renders a progress header (percentage complete) and a
  checklist where each pending item has a **Choose File** control.
- `upload(itemId, input)` posts the selected file as `multipart/form-data`; on success it
  reloads the case so the item flips to "Uploaded" and the bar advances.
- Shows a celebratory "All documents received!" state when everything is uploaded.

### 8.3 Frontend ↔ backend contract

- The front end only ever talks JSON (and one multipart upload). No server-side templating
  of dynamic data beyond injecting the portal token.
- Because data rendering is client-side, the same API can back a future mobile or
  third-party client with no backend change.

---

## 9. Security Model & Considerations

> The current build is an MVP. The items below are **known gaps** to address before
> production — most are resolved or mitigated by the GCP design in §10.

| Area                | Current state                                   | Recommendation                                   |
|---------------------|-------------------------------------------------|--------------------------------------------------|
| Lawyer auth         | None — dashboard is open                         | Add IdP/SSO (e.g. Google Identity, IAP)          |
| Client access       | Single opaque token, non-expiring                | Add expiry, one-time/rotating links, rate limits |
| File validation     | None (type/size/content unchecked)               | Enforce allowed types & size; AV scanning        |
| Filename handling   | Trusts `file.filename`                            | Sanitize / generate server-side names            |
| Transport           | Plain HTTP locally                               | TLS everywhere (Cloud Run provides HTTPS)        |
| Data at rest        | Local SQLite + files                             | Managed DB + object storage with encryption      |
| Concurrency         | SQLite single-writer                             | PostgreSQL (Cloud SQL)                            |
| PII                 | Stores client name/email + documents             | Access controls, retention policy, audit logging |

---

## 10. Deploying to Google Cloud Platform

This section provides a complete, opinionated path to run DocAssist on GCP.

### 10.1 Why the app must change slightly for the cloud

The local app uses two stateful resources that **do not survive on a stateless, autoscaling
runtime** like Cloud Run:

1. **SQLite file** (`docassist.db`) — local to a container instance; lost on restart and
   not shared across instances.
2. **Local `uploads/` directory** — same problem; files written to one instance vanish and
   aren't visible to others.

The cloud-native mapping is:

| Local resource          | GCP service                          | Why                                  |
|-------------------------|--------------------------------------|--------------------------------------|
| SQLite (`docassist.db`) | **Cloud SQL for PostgreSQL**         | Managed, durable, multi-connection   |
| `uploads/` filesystem   | **Cloud Storage (GCS) bucket**       | Durable, scalable object storage     |
| Uvicorn process         | **Cloud Run** (container)            | Serverless, autoscaling, HTTPS, cheap|
| Secrets/credentials     | **Secret Manager**                   | No secrets in code or images         |

> **Alternative (lift-and-shift, no code change):** run the app as-is on a single
> **Compute Engine VM** with a persistent disk (keeps SQLite + local files). Simpler, but
> not autoscaling or highly available. The Cloud Run path below is the recommended target.

### 10.2 Recommended target architecture on GCP

```
        Internet (HTTPS)
              │
              ▼
   ┌─────────────────────┐
   │      Cloud Run      │   ← container running Uvicorn/FastAPI (autoscaled)
   │   docassist service │
   └─────┬──────────┬────┘
         │          │
         │          └────────────▶ Cloud Storage bucket  (document uploads)
         │
         └───────────────────────▶ Cloud SQL (PostgreSQL)  (cases, checklist_items)
                     ▲
                     │ credentials
              ┌──────┴───────┐
              │ Secret Manager│
              └──────────────┘
   Images stored in Artifact Registry; built by Cloud Build.
```

### 10.3 Prerequisites

- A GCP project with **billing enabled**.
- The **gcloud CLI** installed and authenticated (`gcloud auth login`).
- Owner/Editor (or the specific roles: Cloud Run Admin, Cloud SQL Admin, Storage Admin,
  Artifact Registry Admin, Secret Manager Admin, Service Account User).

```bash
# Set your project and a default region
export PROJECT_ID="your-project-id"
export REGION="us-central1"
gcloud config set project "$PROJECT_ID"
gcloud config set run/region "$REGION"

# Enable required APIs
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  storage.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com
```

### 10.4 Code changes required for GCP

These are the minimal modifications to make the app cloud-ready. Keep them behind
environment variables so the app still runs locally with SQLite + local files.

**a) `requirements.txt` — add cloud dependencies**

```
fastapi
uvicorn[standard]
sqlalchemy
python-multipart
jinja2
aiofiles
gunicorn                     # production process manager
psycopg2-binary              # PostgreSQL driver
cloud-sql-python-connector[pg8000]   # secure Cloud SQL connectivity
pg8000                       # pure-python pg driver used by the connector
google-cloud-storage         # GCS uploads
```

**b) `database.py` — choose engine from env**

```python
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

if os.getenv("INSTANCE_CONNECTION_NAME"):
    # Cloud SQL (PostgreSQL) via the Cloud SQL Python Connector
    from google.cloud.sql.connector import Connector, IPTypes
    connector = Connector()

    def getconn():
        return connector.connect(
            os.environ["INSTANCE_CONNECTION_NAME"],
            "pg8000",
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASS"],
            db=os.environ["DB_NAME"],
            ip_type=IPTypes.PUBLIC,
        )

    engine = create_engine("postgresql+pg8000://", creator=getconn, pool_pre_ping=True)
else:
    # Local development: SQLite
    engine = create_engine(
        "sqlite:///./docassist.db", connect_args={"check_same_thread": False}
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

**c) `main.py` — store uploads in GCS when configured**

```python
import os
GCS_BUCKET = os.getenv("GCS_BUCKET")

if GCS_BUCKET:
    from google.cloud import storage
    _gcs = storage.Client()
    _bucket = _gcs.bucket(GCS_BUCKET)

# inside upload_document(...), replace the local file write with:
if GCS_BUCKET:
    blob = _bucket.blob(f"{case.id}/{item_id}_{file.filename}")
    blob.upload_from_string(await file.read(), content_type=file.content_type)
    item.uploaded_file_path = f"gs://{GCS_BUCKET}/{blob.name}"
else:
    case_dir = UPLOAD_DIR / str(case.id)
    case_dir.mkdir(exist_ok=True)
    file_path = case_dir / f"{item_id}_{file.filename}"
    file_path.write_bytes(await file.read())
    item.uploaded_file_path = str(file_path)
```

> Note: `Base.metadata.create_all()` will create the tables in PostgreSQL on first start.
> For real projects, prefer **Alembic** migrations over create-on-start.

**d) `Dockerfile` (new file in project root)**

```dockerfile
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run provides $PORT (default 8080)
ENV PORT=8080
CMD exec gunicorn main:app \
    -k uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:$PORT \
    --workers 2 --timeout 120
```

**e) `.dockerignore` (new file)**

```
venv/
__pycache__/
*.db
uploads/
.git/
Presentation/
ScreenShots/
```

### 10.5 Provision the data layer

**Cloud Storage bucket (uploads):**

```bash
export GCS_BUCKET="${PROJECT_ID}-docassist-uploads"
gcloud storage buckets create "gs://${GCS_BUCKET}" \
  --location="$REGION" \
  --uniform-bucket-level-access
```

**Cloud SQL for PostgreSQL (metadata):**

```bash
export DB_INSTANCE="docassist-pg"
export DB_NAME="docassist"
export DB_USER="docassist_app"
export DB_PASS="$(openssl rand -base64 24)"   # save this securely

# Create a small Postgres instance
gcloud sql instances create "$DB_INSTANCE" \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region="$REGION"

# Create database and application user
gcloud sql databases create "$DB_NAME" --instance="$DB_INSTANCE"
gcloud sql users create "$DB_USER" --instance="$DB_INSTANCE" --password="$DB_PASS"

# Capture the instance connection name (PROJECT:REGION:INSTANCE)
export INSTANCE_CONNECTION_NAME="$(gcloud sql instances describe "$DB_INSTANCE" \
  --format='value(connectionName)')"
echo "$INSTANCE_CONNECTION_NAME"
```

**Store the DB password in Secret Manager:**

```bash
printf "%s" "$DB_PASS" | gcloud secrets create docassist-db-pass --data-file=-
```

### 10.6 Build and push the container

Using **Cloud Build** + **Artifact Registry**:

```bash
# Create an Artifact Registry repo (once)
gcloud artifacts repositories create docassist \
  --repository-format=docker \
  --location="$REGION"

export IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/docassist/app:v1"

# Build the image from the project root and push it
gcloud builds submit --tag "$IMAGE"
```

### 10.7 Deploy to Cloud Run

```bash
# Service account for the running service (least privilege)
gcloud iam service-accounts create docassist-run \
  --display-name="DocAssist Cloud Run"

export RUN_SA="docassist-run@${PROJECT_ID}.iam.gserviceaccount.com"

# Grant access to Cloud SQL, the bucket, and the secret
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUN_SA}" --role="roles/cloudsql.client"
gcloud storage buckets add-iam-policy-binding "gs://${GCS_BUCKET}" \
  --member="serviceAccount:${RUN_SA}" --role="roles/storage.objectAdmin"
gcloud secrets add-iam-policy-binding docassist-db-pass \
  --member="serviceAccount:${RUN_SA}" --role="roles/secretmanager.secretAccessor"

# Deploy
gcloud run deploy docassist \
  --image="$IMAGE" \
  --service-account="$RUN_SA" \
  --add-cloudsql-instances="$INSTANCE_CONNECTION_NAME" \
  --set-env-vars="INSTANCE_CONNECTION_NAME=${INSTANCE_CONNECTION_NAME},DB_USER=${DB_USER},DB_NAME=${DB_NAME},GCS_BUCKET=${GCS_BUCKET}" \
  --set-secrets="DB_PASS=docassist-db-pass:latest" \
  --allow-unauthenticated \
  --region="$REGION" \
  --cpu=1 --memory=512Mi --min-instances=0 --max-instances=5
```

On success, Cloud Run prints a public **HTTPS URL** (e.g.
`https://docassist-xxxxx-uc.a.run.app`). Open it to reach the lawyer dashboard; client
portal links generated by the app will use this same domain automatically (they are built
from the request origin in the browser).

### 10.8 Post-deployment checklist

- [ ] **Smoke test:** open the URL, create a case, copy the portal link, upload a file as a
      client, confirm progress updates.
- [ ] **Verify storage:** `gcloud storage ls "gs://${GCS_BUCKET}/**"` shows the uploaded object.
- [ ] **Verify DB:** connect via `gcloud sql connect "$DB_INSTANCE" --user="$DB_USER"` and
      `SELECT * FROM cases;`.
- [ ] **Lock down access:** remove `--allow-unauthenticated` and front the lawyer dashboard
      with **Identity-Aware Proxy (IAP)** or Google sign-in; keep only the client portal
      paths public if needed.
- [ ] **Custom domain & TLS:** map a domain via Cloud Run domain mappings (TLS is managed).
- [ ] **Observability:** review logs/metrics in Cloud Logging & Cloud Monitoring; add
      uptime checks and alerts.
- [ ] **Backups:** ensure Cloud SQL automated backups + point-in-time recovery are on;
      set a GCS lifecycle/retention policy for documents.
- [ ] **Migrations:** adopt Alembic before further schema changes (replace create-on-start).
- [ ] **Hardening:** add file type/size validation and server-side filenames (see §9).

### 10.9 Scaling notes (toward "big data")

As volume grows, the same architecture extends cleanly:

- **Storage:** GCS already scales to billions of objects; add lifecycle tiers
  (Standard → Nearline → Coldline) for old documents.
- **Database:** scale Cloud SQL vertically, add read replicas, or migrate to AlloyDB /
  Spanner for very high concurrency.
- **Ingestion:** for bursty uploads, push post-upload processing to **Pub/Sub + Cloud
  Functions / Cloud Run jobs** (e.g. virus scan, OCR, classification).
- **Analytics:** stream metadata to **BigQuery** for cross-firm dashboards (avg. completion
  time, bottleneck document types).
- **AI verification:** use **Document AI / Vertex AI** to classify uploads and confirm the
  correct, complete document was provided.

---

## 11. Appendix: Configuration & Environment Variables

| Variable                   | Used by      | Local default        | Cloud value                                |
|----------------------------|--------------|----------------------|--------------------------------------------|
| `INSTANCE_CONNECTION_NAME` | `database.py`| _(unset → SQLite)_   | `PROJECT:REGION:INSTANCE` (Cloud SQL)      |
| `DB_USER`                  | `database.py`| —                    | `docassist_app`                            |
| `DB_PASS`                  | `database.py`| —                    | from Secret Manager (`docassist-db-pass`)  |
| `DB_NAME`                  | `database.py`| —                    | `docassist`                                |
| `GCS_BUCKET`               | `main.py`    | _(unset → local fs)_ | `${PROJECT_ID}-docassist-uploads`          |
| `PORT`                     | Dockerfile   | `8000`               | `8080` (provided by Cloud Run)             |

**Local run (unchanged):**

```bash
uvicorn main:app --reload      # uses SQLite + local uploads/ when cloud vars are unset
```

**Cloud run model:** the same code path activates PostgreSQL + GCS purely based on the
presence of `INSTANCE_CONNECTION_NAME` and `GCS_BUCKET`, so there is **one codebase** for
both environments.

---

*Document maintained alongside the DocAssist codebase. For a functional overview see
[DOCUMENTATION.md](DOCUMENTATION.md); for quick start see [README.md](README.md).*

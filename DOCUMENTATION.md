# DocAssist — Project Documentation

A detailed technical and functional walkthrough of **DocAssist**, a document-collection
assistant for lawyers.

---

## 1. What is this project?

**DocAssist** solves a single, very common pain point for lawyers:

> *"Lawyers spend too much time chasing clients for documents."*

Clients typically send required paperwork **incomplete and in pieces**, forcing the
lawyer to keep following up. DocAssist replaces that back-and-forth with a structured,
self-service workflow:

1. A **lawyer** creates a *case* and defines a **checklist** of documents they need
   (e.g. Government ID, Medical Records, Signed Forms).
2. The system generates a **unique, shareable link** (a "client portal").
3. The lawyer sends that link to the **client**.
4. The client opens the link and **uploads each document** one at a time.
5. The lawyer watches **real-time progress** ("2/3 received") on their dashboard.

This is deliberately a **minimum viable product (MVP)**. There is no AI, no login system,
and no email automation yet — those are intentionally deferred (see
[Roadmap](#9-roadmap--whats-intentionally-not-built-yet)). The original product thinking
is captured in [Problem.md](Problem.md).

---

## 2. Tech stack

| Layer        | Technology                                    |
|--------------|-----------------------------------------------|
| Backend      | [FastAPI](https://fastapi.tiangolo.com/)      |
| ORM / DB     | SQLAlchemy 2.0 (typed `Mapped` style) + SQLite |
| Validation   | Pydantic (request/response schemas)           |
| Frontend     | Vanilla HTML / CSS / JavaScript via Jinja2 templates |
| File storage | Local filesystem (`uploads/` directory)       |
| Server       | Uvicorn (ASGI)                                |

Dependencies are pinned in [requirements.txt](requirements.txt):
`fastapi`, `uvicorn`, `sqlalchemy`, `python-multipart`, `jinja2`, `aiofiles`.

---

## 3. Project structure

```
Asel/
├── main.py            # FastAPI app: all routes (API + HTML pages)
├── database.py        # SQLAlchemy engine, session, Base, get_db() dependency
├── models.py          # ORM models: Case, ChecklistItem
├── schemas.py         # Pydantic schemas (request/response shapes)
├── requirements.txt   # Python dependencies
├── docassist.db       # SQLite database file (auto-created on first run)
├── templates/
│   ├── dashboard.html # Lawyer-facing dashboard (single-page app)
│   └── portal.html    # Client-facing upload portal
├── uploads/           # Uploaded files, organized per case: uploads/<case_id>/
├── sample_docs/       # Example documents (test data)
├── venv/              # Pre-built Python virtual environment
├── README.md          # Quick-start guide
├── Problem.md         # Original product/problem framing
└── DOCUMENTATION.md   # ← this file
```

---

## 4. How to run it

From the project root (`c:\Asel`) in PowerShell:

```powershell
# 1. Activate the bundled virtual environment
.\venv\Scripts\Activate.ps1

# 2. Start the dev server (auto-reloads on code changes)
uvicorn main:app --reload
```

> If PowerShell blocks the activation script, either run
> `Set-ExecutionPolicy -Scope Process -Bypass` once for the session, or skip activation
> and call the venv binary directly: `.\venv\Scripts\uvicorn.exe main:app --reload`.

Then open:

- **Lawyer Dashboard** → http://localhost:8000
- **Interactive API docs (Swagger UI)** → http://localhost:8000/docs

The database (`docassist.db`) and `uploads/` folder are created automatically on first
run — no setup step required.

---

## 5. Data model

Defined in [models.py](models.py). Two tables with a one-to-many relationship.

### `Case` (table: `cases`)

| Field            | Type      | Notes                                              |
|------------------|-----------|----------------------------------------------------|
| `id`             | int (PK)  | Auto-increment primary key                         |
| `title`          | str(200)  | Case title, e.g. "Personal Injury — John Doe"      |
| `client_name`    | str(200)  | Client's name                                      |
| `client_email`   | str(200)  | Client's email                                     |
| `access_token`   | str(16)   | Unique random token (`uuid4().hex[:16]`) for the portal link |
| `created_at`     | datetime  | UTC creation timestamp                             |
| `checklist_items`| relation  | One-to-many → `ChecklistItem` (cascade delete)     |

### `ChecklistItem` (table: `checklist_items`)

| Field                | Type        | Notes                                  |
|----------------------|-------------|----------------------------------------|
| `id`                 | int (PK)    | Auto-increment primary key             |
| `case_id`            | int (FK)    | References `cases.id`                   |
| `name`               | str(200)    | Document name, e.g. "Government ID"     |
| `description`        | text (null) | Optional guidance for the client        |
| `is_received`        | bool        | `True` once the client uploads a file   |
| `uploaded_file_path` | str (null)  | Path to the stored file on disk         |
| `uploaded_at`        | datetime    | When the upload happened (UTC)          |

**Key design points:**

- The **`access_token`** is what makes the client portal work without logins — anyone
  with the link can view and upload for that one case. (This is also a security
  consideration; see [Security notes](#8-security--limitations).)
- Deleting a case **cascades** to delete its checklist items
  (`cascade="all, delete-orphan"`).

---

## 6. API reference

All routes are defined in [main.py](main.py).

### Cases (lawyer side)

| Method   | Endpoint                       | Description                          |
|----------|--------------------------------|--------------------------------------|
| `POST`   | `/api/cases`                   | Create a case (optionally with an initial checklist) |
| `GET`    | `/api/cases`                   | List all cases with progress summary |
| `GET`    | `/api/cases/{case_id}`         | Get one case + its full checklist    |
| `DELETE` | `/api/cases/{case_id}`         | Delete a case and all its items      |

### Checklist items (lawyer side)

| Method   | Endpoint                          | Description                       |
|----------|-----------------------------------|-----------------------------------|
| `POST`   | `/api/cases/{case_id}/checklist`  | Add a checklist item to a case    |
| `DELETE` | `/api/checklist/{item_id}`        | Remove a checklist item           |

### Client portal (token-based, no login)

| Method   | Endpoint                                   | Description                       |
|----------|--------------------------------------------|-----------------------------------|
| `GET`    | `/api/client/{token}`                      | View a case via its access token  |
| `POST`   | `/api/client/{token}/upload/{item_id}`     | Upload a file for a checklist item |

### HTML pages

| Method | Endpoint           | Serves                              |
|--------|--------------------|-------------------------------------|
| `GET`  | `/`                | Lawyer dashboard (`dashboard.html`) |
| `GET`  | `/portal/{token}`  | Client upload portal (`portal.html`)|

**Request/response shapes** are defined as Pydantic models in [schemas.py](schemas.py):
`CaseCreate`, `CaseOut`, `CaseSummary`, `ChecklistItemCreate`, `ChecklistItemOut`.

---

## 7. End-to-end workflow

### Lawyer flow (dashboard at `/`)

1. **Create a case** — click **+ New Case**, fill in title / client name / email, and
   add one or more checklist items, then **Create Case**.
   → `POST /api/cases`
2. **Open a case** — click the case title to enter the detail view. Here you can:
   - **Copy the client portal link** to send to the client.
   - **+ Add Item** to add more required documents (`POST /api/cases/{id}/checklist`).
   - **Remove** an item (`DELETE /api/checklist/{id}`).
   - **Delete** the whole case (`DELETE /api/cases/{id}`).
3. **Track progress** — the case list shows a badge (`1/3` or **Complete**) and a green
   progress bar that updates as the client uploads.

The dashboard is a small single-page app: [dashboard.html](templates/dashboard.html)
fetches from the JSON API and re-renders. It has two views toggled in JS — a **list view**
and a **detail view**.

### Client flow (portal at `/portal/{token}`)

1. Client opens the link → [portal.html](templates/portal.html) loads the case via
   `GET /api/client/{token}`.
2. Each required document shows with a **Choose File** button.
3. Selecting a file triggers `POST /api/client/{token}/upload/{item_id}`. The file is
   saved to `uploads/<case_id>/<item_id>_<filename>`, the item is marked **received**, and
   the progress bar advances.
4. When everything is uploaded, the client sees an **"All documents received!"**
   confirmation.

### How an upload is stored

In [main.py](main.py#L116) (`upload_document`):

1. Look up the case by `token`; 404 if invalid.
2. Look up the checklist item by `item_id` **scoped to that case**; 404 if not found.
3. Create `uploads/<case_id>/` if needed.
4. Save the file bytes as `<item_id>_<original_filename>`.
5. Set `is_received = True`, record the path and `uploaded_at` timestamp, and commit.

---

## 8. Security & limitations

This is an MVP and not yet production-hardened. Notable points:

- **No authentication for lawyers** — the dashboard at `/` is open to anyone who can
  reach the server. There is no user accounts / login layer.
- **Access tokens are the only gate** for the client portal. Anyone with the 16-character
  token link can view the case and upload. Tokens don't expire.
- **No file validation** — uploads are not checked for type, size, or content. A
  production version should restrict extensions/size and scan/validate files.
- **Filename handling** — the stored name is `f"{item_id}_{file.filename}"`. The original
  client filename is trusted; consider sanitizing it to avoid path/encoding issues.
- **SQLite + `check_same_thread=False`** is fine for local/dev and light usage, but not
  ideal for high-concurrency production. Swap to PostgreSQL for scale.
- **Re-uploading** overwrites the previous file for that item (same path), and there is no
  version history.

---

## 9. Roadmap — what's intentionally NOT built yet

Per [Problem.md](Problem.md), the strategy is "start with pain + workflow, not AI."
Deferred features include:

- **Auto reminders** — automatically email clients about missing documents.
- **AI document checks** — read an uploaded document and verify it's the correct/complete
  one.
- **Auto-detect missing info** and **smart suggestions**.
- **Editing existing cases** — currently the UI can only add/remove checklist items; it
  cannot edit a case's title/client/email or rename an item (no update/PATCH endpoints
  exist yet).
- **Lawyer authentication & multi-user accounts.**

---

## 10. Quick reference: file → responsibility

| File                              | Responsibility                                        |
|-----------------------------------|-------------------------------------------------------|
| [main.py](main.py)                | FastAPI app, all API routes, page rendering, uploads  |
| [database.py](database.py)        | DB engine, session factory, `Base`, `get_db` dependency |
| [models.py](models.py)            | `Case` and `ChecklistItem` ORM models                 |
| [schemas.py](schemas.py)          | Pydantic request/response schemas                     |
| [templates/dashboard.html](templates/dashboard.html) | Lawyer SPA dashboard            |
| [templates/portal.html](templates/portal.html)       | Client upload portal            |
| [requirements.txt](requirements.txt) | Python dependencies                                |

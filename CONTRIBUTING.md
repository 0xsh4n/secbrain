# Contributing to SecBrain

Thank you for your interest in contributing to **SecBrain**! SecBrain is a model-independent cybersecurity knowledge platform, AI copilot, and agent integration runtime.

This guide outlines our development setup, architecture principles, coding standards, and testing procedures for developers and contributors.

---

## Table of Contents

- [Code of Conduct & Safety](#code-of-conduct--safety)
- [Prerequisites](#prerequisites)
- [Development Setup](#development-setup)
  - [Docker Setup (Recommended)](#1-docker-compose-recommended)
  - [Native Development (No Docker)](#2-native-development-backend--frontend)
- [Architecture & Key Subsystems](#architecture--key-subsystems)
  - [Backend Services (`backend/app/services/`)](#backend-services)
  - [Chat & GenAI Copilot Engine](#chat--genai-copilot-engine)
  - [Live Cyber Call & Audio Synthesis](#live-cyber-call--audio-synthesis)
  - [Model Context Protocol (MCP) Server](#model-context-protocol-mcp-server)
- [Quality Gates & Testing](#quality-gates--testing)
  - [Running Backend Tests](#running-backend-tests)
  - [Running the Retrieval Evaluation Harness](#running-the-retrieval-evaluation-harness)
  - [Frontend Type-Checking & Build](#frontend-type-checking--build)
  - [Database Migrations (Alembic)](#database-migrations-alembic)
- [Key Architectural Guidelines](#key-architectural-guidelines)
- [Pull Request Checklist](#pull-request-checklist)

---

## Code of Conduct & Safety

SecBrain is designed to index, structure, and reason over cybersecurity knowledge (CVEs, security standards, remediation advice, compliance, and architectural documentation).

* **Defensive Focus:** Contributions must emphasize defense, vulnerability analysis, security education, auditing, and remediation.
* **Prompt Injection Defense:** External documents and user uploads are treated strictly as **DATA**, never instructions. Always preserve the boundary between trusted system prompts and untrusted evidence text.

---

## Prerequisites

* **Python:** 3.12 or higher (verified on 3.12–3.14).
* **Node.js:** 20+ and npm.
* **Docker:** Docker Desktop or Docker Engine with Docker Compose v2+.
* **Ollama (Optional, for local AI):** Install Ollama on your host machine to run local models (e.g. `qwen2.5:3b`, `nomic-embed-text`).

---

## Development Setup

### 1. Docker Compose (Recommended)

The simplest way to bring up the full environment (PostgreSQL + FastAPI backend + Next.js frontend):

```bash
# 1. Copy the environment configuration
cp .env.example .env

# 2. Build and launch all services
docker compose up --build
```

Access the services:
* **Web UI:** [http://localhost:3000](http://localhost:3000)
* **Backend API (Swagger Docs):** [http://localhost:8000/docs](http://localhost:8000/docs)
* **Health Check:** [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

### 2. Native Development (Backend & Frontend)

#### Backend Setup

```bash
cd backend

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate       # On Windows: .venv\Scripts\Activate.ps1

# Install pinned dependencies
pip install -r requirements.txt

# Configure environment (defaults to SQLite + offline deterministic models)
cp .env.example .env

# Run database migrations
alembic upgrade head

# Bootstrap admin account and seed sample corpus
python -m app.cli bootstrap
python -m app.cli seed-samples

# Start the FastAPI server with auto-reload
uvicorn app.main:app --reload --port 8000
```

#### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Configure environment
cp .env.local.example .env.local

# Run Next.js in development mode
npm run dev
```

---

## Architecture & Key Subsystems

```
secbrain/
├── backend/
│   ├── alembic/                # Database migrations
│   ├── app/
│   │   ├── api/                # FastAPI routers (thin; delegation only)
│   │   ├── core/               # Security, JWT, token hashing, taxonomies
│   │   ├── mcp/                # Model Context Protocol stdio server
│   │   ├── models/             # SQLAlchemy ORM models
│   │   ├── schemas/            # Pydantic request & response validation
│   │   └── services/           # Core domain logic (framework-agnostic)
│   ├── eval/                   # Deterministic retrieval evaluation harness
│   └── tests/                  # Automated pytest suite (45+ tests)
├── frontend/
│   ├── app/                    # Next.js App Router pages
│   │   └── (app)/chat/         # Copilot, Live Call overlay, Markdown renderer
│   ├── components/             # Reusable UI cards, buttons, inputs
│   └── lib/                    # API client, auth context, Web Audio/Speech voice engine
└── docs/                       # Architecture, threat model, API, agents guides
```

### Backend Services

All business logic lives inside `backend/app/services/` and is strictly decoupled from FastAPI routers. This ensures that the REST API, MCP server, CLI commands, and evaluation harness all share identical logic and access controls:

* **`ingestion.py` & `extraction.py`:** Handles document ingestion across PDF, MD, HTML, DOCX, plain text, and URLs with SSRF protection and duplicate detection.
* **`chunking.py`:** Heading-aware, bounded chunking with configurable overlap.
* **`embeddings.py`:** Provider abstraction (`fake`, `ollama`, `openai`). Every embedding model records a distinct version tag (`provider:model:dim`) to prevent mixing incompatible vector spaces.
* **`retrieval.py`:** Hybrid retrieval fusing cosine vector similarity, IDF-weighted lexical matching, and security identifier boosting (CVE, CWE, CAPEC, ATT&CK).
* **`answer.py` & `llm.py`:** Generates grounded answers, citations (`[E1]`), and technical code using SecBrain Copilot. Includes automatic conversational query bypass for instant greetings.

### Chat & GenAI Copilot Engine

* **Multi-Turn Context:** The chat service records messages in database-backed conversation threads and feeds the last 6 turns as conversational context.
* **Markdown & Code Rendering:** [`frontend/app/(app)/chat/MarkdownMessage.tsx`](frontend/app/(app)/chat/MarkdownMessage.tsx) parses fenced code blocks, provides a 1-click **"Copy code"** button, and renders inline tags and citations.
* **Universal SSE Streaming:** The `/conversations/{id}/stream` endpoint delivers word-by-word streaming over Server-Sent Events.

### Live Cyber Call & Audio Synthesis

* **Full-Duplex Voice Call:** [`frontend/app/(app)/chat/VoiceCallOverlay.tsx`](frontend/app/(app)/chat/VoiceCallOverlay.tsx) implements an interactive, hands-free tactical call HUD.
* **Web Audio Visualizer:** Connects user microphone input to a Web Audio `AnalyserNode` to draw a real-time reactive sound wave on an HTML5 canvas.
* **Hacker Girl Persona:** Configured in [`frontend/lib/voice.ts`](frontend/lib/voice.ts) using the Web Speech API (`pitch: 1.25`, `rate: 1.08`) with synthetic sci-fi uplink chirps and automatic code-block stripping.

### Model Context Protocol (MCP) Server

SecBrain exposes a read-only MCP stdio server in [`backend/app/mcp/server.py`](backend/app/mcp/server.py). External agent runners (Claude Desktop, Cursor, AutoGen, CrewAI) can connect using an authorized SecBrain API key to search the knowledge base and retrieve document passages. See [`docs/AGENTS.md`](docs/AGENTS.md).

---

## Quality Gates & Testing

Before submitting a pull request, ensure all tests and quality checks pass.

### Running Backend Tests

The test suite covers authentication, SSRF boundaries, ingestion state transitions, vector retrieval, authorization, API keys, and MCP handlers:

```bash
cd backend
pytest -v
```

> [!NOTE]
> `tests/conftest.py` configures an isolated in-memory SQLite database and test client. Tests never touch your production database.

### Running the Retrieval Evaluation Harness

SecBrain includes a deterministic evaluation harness that tests retrieval precision, recall@k, Mean Reciprocal Rank (MRR), citation validity, and abstention on ungrounded queries:

```bash
cd backend
python -m eval.run_eval
```

### Frontend Type-Checking & Build

Verify that the Next.js frontend builds without TypeScript or compilation errors:

```bash
cd frontend
npm run build
```

### Database Migrations (Alembic)

When modifying database models in `backend/app/models/`:

```bash
cd backend

# 1. Generate an Alembic migration script
alembic revision --autogenerate -m "describe_your_change"

# 2. Inspect the generated migration in backend/alembic/versions/

# 3. Apply the migration
alembic upgrade head
```

---

## Key Architectural Guidelines

1. **Keep Services Framework-Agnostic:**  
   Do not import FastAPI `Request`, `HTTPException`, or `Depends` inside `backend/app/services/`. Raise standard Python exceptions (`ValueError`, `PermissionError`) and map them in the `api/` layer.

2. **Model Independence:**  
   Never hardcode assumptions about a specific LLM tokenizer, model architecture, or remote API. Use configuration options in `backend/app/config.py`.

3. **Hardware Efficiency:**  
   Keep local model defaults optimized for consumer GPUs (e.g. 4 GB VRAM / GTX 1650). Use context windows $\le 4096$, top-k retrieval $\le 4$, and keep models warm with `"keep_alive": "30m"`.

4. **Zero-Trust for Evidence Data:**  
   Never allow retrieved document content to override or alter system instructions. Document passages must always be framed within the untrusted evidence block.

---

## Pull Request Checklist

- [ ] All 45+ backend tests pass (`pytest`).
- [ ] Evaluation harness clears all quality thresholds (`python -m eval.run_eval`).
- [ ] Frontend builds cleanly with zero errors (`npm run build`).
- [ ] Documentation updated in `docs/` or `README.md` if adding or changing features.
- [ ] New database columns or tables include an Alembic migration script.
- [ ] Environment variable changes are reflected in `.env.example` and `backend/.env.example`.

# Sentry Rotation AI Agent — POC

A multi-agent system that automates Sentry alert triage using Gemini Flash. Built with FastAPI + Pydantic, with a Slack-like demo UI.

## Architecture

Three agents run in sequence for every alert:

```
Gatekeeper → Architect → Diplomat
```

| Agent          | Role                                                                               |
| -------------- | ---------------------------------------------------------------------------------- |
| **Gatekeeper** | Calls Gemini to classify the alert: valid bug, noise, duplicate, or high priority  |
| **Architect**  | Routes to the owning team via `domain_map.yaml`, creates a Jira ticket or archives |
| **Diplomat**   | Composes the Slack thread message, applies emoji reaction, escalates if needed     |

Sentry and Jira are mocked as JSON files. Slack is a custom UI.

---

## Prerequisites

- Python 3.11+
- A [Gemini API key](https://aistudio.google.com/app/apikey) (free tier works)

---

## Setup

**1. Create a virtual environment**

```bash
python -m venv .venv
source .venv/bin/activate      # macOS / Linux
.venv\Scripts\activate         # Windows
```

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

**3. Configure environment**

```bash
cp .env.example .env
```

Open `.env` and set your Gemini API key:

```env
GEMINI_API_KEY=your_key_here
CONFIDENCE_THRESHOLD=0.75
```

---

## Run

```bash
uvicorn main:app --reload
```

Open **http://localhost:8000** in your browser.

---

## Demo walkthrough

The UI shows a queue of 4 pre-loaded Sentry alerts, one per scenario:

| Alert        | Scenario                                   | Expected outcome                    |
| ------------ | ------------------------------------------ | ----------------------------------- |
| `SENTRY-001` | Valid bug                                  | Architect creates a new Jira ticket |
| `SENTRY-002` | High priority (`ForeignKeyViolationError`) | Ticket created + leads escalated    |
| `SENTRY-003` | Noise (infra / deploy)                     | Resolved without a ticket           |
| `SENTRY-004` | Duplicate (NF-21910 exists)                | Archived in Sentry                  |

Click **→ triage this alert** on any card to trigger the agent pipeline. The right panel shows each agent's decision in real time.

---

## Project structure

```
sentry-poc/
├── main.py                  # FastAPI app + static file serving
├── config.py                # Settings via pydantic-settings + .env
├── models.py                # All Pydantic types
├── agents.py                # Gatekeeper, Architect, Diplomat logic
├── llm_client.py            # Gemini Flash calls with structured JSON output
├── mock_db.py               # File-based Sentry + Jira mock (read/write JSON)
├── domain_map.py            # YAML loader — URL pattern → team → leads
├── data/
│   ├── sentry_alerts.json   # Mock Sentry alerts (source of truth for demo)
│   ├── jira_tickets.json    # Existing Jira tickets (modified at runtime)
│   └── domain_map.yaml      # Team ownership + triage rotation schedule
├── routers/
│   └── alerts.py            # POST /api/alerts/{id}/process
└── static/
    └── index.html           # Full demo UI
```

---

## API

The UI consumes these endpoints directly. You can also hit them manually:

```bash
# List all alerts
GET  /api/alerts

# Get a single alert
GET  /api/alerts/{alert_id}

# Run the agent pipeline on an alert
POST /api/alerts/{alert_id}/process

# OpenAPI docs
GET  /docs
```

---

## Extending

**Add a new alert scenario** — edit `data/sentry_alerts.json` and add an entry. Set `scenario` to one of: `valid_bug`, `high_priority`, `noise`, `duplicate`.

**Add a team** — edit `data/domain_map.yaml`. Add a new entry under `teams` with `name`, `slack_handle`, `leads`, and `patterns` (URL path substrings).

**Change triage owner** — update `triage_rotation.current_owner` in `data/domain_map.yaml`.

**Swap the LLM** — all Gemini calls are isolated in `llm_client.py`. Replace `gatekeeper_classify` and `diplomat_compose` with any other provider.

---

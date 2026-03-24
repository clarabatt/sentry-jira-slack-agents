import json
from pathlib import Path
from models import Priority, SentryAlert, JiraTicket

DATA_DIR = Path(__file__).parent / "data"


def load_sentry_alerts() -> list[SentryAlert]:
    raw = json.loads((DATA_DIR / "sentry_alerts.json").read_text())
    return [SentryAlert(**a) for a in raw]


def get_sentry_alert(alert_id: str) -> SentryAlert | None:
    return next((a for a in load_sentry_alerts() if a.id == alert_id), None)


def load_jira_tickets() -> list[JiraTicket]:
    raw = json.loads((DATA_DIR / "jira_tickets.json").read_text())
    return [JiraTicket(**t) for t in raw]


def create_jira_ticket(summary: str, priority: Priority, url_path: str, sentry_id: str) -> JiraTicket:
    tickets = load_jira_tickets()
    next_num = 21922 + len(tickets)
    ticket = JiraTicket(
        id=f"NF-{next_num}",
        key=f"NF-{next_num}",
        summary=f"[Sentry] {summary}",
        status="GROOMING",
        priority=priority,
        assignee=None,
        sentry_issue_id=sentry_id,
        url_path=url_path,
        created_at="2026-03-20T09:30:00Z",
    )
    tickets.append(ticket)
    # In a real implementation, we would persist this to the database.
    # raw = [t.model_dump() for t in tickets]
    # (DATA_DIR / "jira_tickets.json").write_text(json.dumps(raw, indent=2))
    return ticket

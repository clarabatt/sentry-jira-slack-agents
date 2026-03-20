from models import (
    AgentContext, GatekeeperDecision, ArchitectDecision,
    DiplomatAction, SentryAlert
)
from mock_db import (
    find_jira_ticket_by_sentry_id, find_jira_ticket_by_path,
    create_jira_ticket
)
from domain_map import lookup_team, get_triage_owner
from llm_client import gatekeeper_classify, diplomat_compose
from config import get_settings


# ─── Gatekeeper ────────────────────────────────────────────────────────────────

async def run_gatekeeper(alert: SentryAlert) -> GatekeeperDecision:
    # Check for existing ticket (dedup)
    existing = find_jira_ticket_by_sentry_id(alert.id)
    existing_id = existing.key if existing else None

    decision = await gatekeeper_classify(alert.model_dump(), existing_id)
    return decision


# ─── Architect ─────────────────────────────────────────────────────────────────

async def run_architect(alert: SentryAlert, gk: GatekeeperDecision) -> ArchitectDecision:
    team = lookup_team(alert.url_path)
    triage_owner = get_triage_owner()

    action = _decide_action(gk)
    ticket_key = None

    if action == "create_ticket":
        priority = "Highest" if gk.is_high_priority else "Medium"
        ticket = create_jira_ticket(
            summary=alert.title,
            priority=priority,
            url_path=alert.url_path,
            sentry_id=alert.id,
        )
        ticket_key = ticket.key

    elif action == "archive" and gk.existing_ticket_id:
        ticket_key = gk.existing_ticket_id

    return ArchitectDecision(
        team=team["name"],
        team_slack_handle=team["slack_handle"],
        leads=team["leads"],
        action=action,
        jira_ticket_key=ticket_key,
        triage_owner=triage_owner,
    )


def _decide_action(gk: GatekeeperDecision) -> str:
    if gk.classification == "duplicate":
        return "archive"
    if gk.classification == "noise":
        return "resolve"
    if gk.classification in ("valid_bug", "high_priority"):
        return "create_ticket"
    return "create_ticket"


# ─── Diplomat ──────────────────────────────────────────────────────────────────

async def run_diplomat(alert: SentryAlert, gk: GatekeeperDecision, arch: ArchitectDecision) -> DiplomatAction:
    action_label = arch.action
    if gk.is_high_priority:
        action_label = "escalate"

    diplomat = await diplomat_compose(
        action=action_label,
        team=arch.team,
        ticket_key=arch.jira_ticket_key,
        reasoning=gk.reasoning,
        alert_title=alert.title,
    )

    # Inject escalation targets for high priority
    if gk.is_high_priority:
        diplomat.escalation_targets = arch.leads + [arch.triage_owner]

    return diplomat

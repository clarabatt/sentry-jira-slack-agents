import traceback

import logging

from models import (
    Action, Classification, GatekeeperDecision, ArchitectDecision,
    DiplomatAction, Priority, SentryAlert
)
from mcp_gatekeeper import run_gatekeeper as run_gatekeeper_mcp
from mock_db import create_jira_ticket
from domain_map import lookup_team, get_triage_owner
from llm_client import diplomat_compose

logger = logging.getLogger(__name__)

# ─── Gatekeeper ────────────────────────────────────────────────────────────────

async def run_gatekeeper(alert: SentryAlert) -> GatekeeperDecision:
    logger.info("Gatekeeper start", extra={"alert": alert.dict()})
    decision = None
    try:
        result = await run_gatekeeper_mcp(alert.model_dump())
        logger.info("Gatekeeper got result", extra={"result": result})
        decision = GatekeeperDecision(**result)
    except* Exception as e:
        logger.error("MCP sub-process failed", exc_info=True)
        logger.error("MCP exception type=%s msg=%s", type(e), e, stack_info=True)
        logger.error("Traceback:\n%s", traceback.format_exc())
        decision = GatekeeperDecision(
            classification=Classification.error,
            confidence=0.0,
            reasoning="MCP sub-process failed.",
            is_high_priority=False
        )
    return decision


# ─── Architect ─────────────────────────────────────────────────────────────────

async def run_architect(alert: SentryAlert, gk: GatekeeperDecision) -> ArchitectDecision:
    team = lookup_team(alert.url_path)
    triage_owner = get_triage_owner()

    action = _decide_action(gk)
    ticket_key = None

    if action == Action.create_ticket:
        priority = Priority.highest if gk.is_high_priority else Priority.medium
        ticket = create_jira_ticket(
            summary=alert.title,
            priority=priority,
            url_path=alert.url_path,
            sentry_id=alert.id,
        )
        ticket_key = ticket.key

    elif action == Action.archive and gk.existing_ticket_id:
        ticket_key = gk.existing_ticket_id

    return ArchitectDecision(
        team=team["name"],
        team_slack_handle=team["slack_handle"],
        leads=team["leads"],
        action=action,
        jira_ticket_key=ticket_key,
        triage_owner=triage_owner,
    )


def _decide_action(gk: GatekeeperDecision) -> Action:
    if gk.classification == Classification.error:
        return Action.manual_triage
    if gk.classification == Classification.duplicate:
        return Action.archive
    if gk.classification == Classification.noise:
        return Action.resolve
    if gk.classification in (Classification.valid_bug, Classification.high_priority):
        return Action.create_ticket
    return Action.create_ticket


# ─── Diplomat ──────────────────────────────────────────────────────────────────

async def run_diplomat(alert: SentryAlert, gk: GatekeeperDecision, arch: ArchitectDecision) -> DiplomatAction:
    action_label = arch.action
    if gk.is_high_priority and arch.action == Action.create_ticket:
        action_label = Action.escalate
    elif gk.classification == Classification.error:
        action_label = Action.system_failure

    diplomat = await diplomat_compose(
        action=action_label,
        team=arch.team,
        ticket_key=arch.jira_ticket_key,
        reasoning=gk.reasoning,
        alert_title=alert.title,
    )

    if gk.is_high_priority:
        diplomat.escalation_targets = arch.leads + [arch.triage_owner]

    return diplomat

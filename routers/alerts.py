from fastapi import APIRouter, HTTPException
from models import SentryAlert, AgentContext, AlertProcessingResult, ProcessingStep
from mock_db import load_sentry_alerts, get_sentry_alert
from agents import run_gatekeeper, run_architect, run_diplomat

router = APIRouter(prefix="/api", tags=["alerts"])


@router.get("/alerts", response_model=list[SentryAlert])
async def list_alerts():
    return load_sentry_alerts()


@router.get("/alerts/{alert_id}", response_model=SentryAlert)
async def get_alert(alert_id: str):
    alert = get_sentry_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.post("/alerts/{alert_id}/process", response_model=AlertProcessingResult)
async def process_alert(alert_id: str):
    alert = get_sentry_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    steps: list[ProcessingStep] = []
    ctx = AgentContext(alert=alert)

    # ── Step 1: Gatekeeper ──────────────────────────────────────────────────
    steps.append(ProcessingStep(agent="Gatekeeper", status="running"))
    try:
        ctx.gatekeeper = await run_gatekeeper(alert)
        steps[-1].status = "done"
        steps[-1].result = ctx.gatekeeper.model_dump()
    except Exception as e:
        steps[-1].status = "error"
        steps[-1].result = {"error": str(e)}
        return _build_result(alert_id, steps, "error", ctx)

    # ── Step 2: Architect ───────────────────────────────────────────────────
    steps.append(ProcessingStep(agent="Architect", status="running"))
    try:
        ctx.architect = await run_architect(alert, ctx.gatekeeper)
        steps[-1].status = "done"
        steps[-1].result = ctx.architect.model_dump()
    except Exception as e:
        steps[-1].status = "error"
        steps[-1].result = {"error": str(e)}
        return _build_result(alert_id, steps, "error", ctx)

    # ── Step 3: Diplomat ────────────────────────────────────────────────────
    steps.append(ProcessingStep(agent="Diplomat", status="running"))
    try:
        ctx.diplomat = await run_diplomat(alert, ctx.gatekeeper, ctx.architect)
        steps[-1].status = "done"
        steps[-1].result = ctx.diplomat.model_dump()
    except Exception as e:
        steps[-1].status = "error"
        steps[-1].result = {"error": str(e)}
        return _build_result(alert_id, steps, "error", ctx)

    return _build_result(alert_id, steps, "completed", ctx)


def _build_result(alert_id: str, steps: list, status: str, ctx: AgentContext) -> AlertProcessingResult:
    slack_mock = {}
    if ctx.diplomat:
        slack_mock = {
            "reaction": ctx.diplomat.emoji,
            "thread_message": ctx.diplomat.thread_message,
            "escalation_message": ctx.diplomat.escalation_message,
            "escalation_targets": ctx.diplomat.escalation_targets,
        }
    if ctx.architect:
        slack_mock["team"] = ctx.architect.team
        slack_mock["ticket"] = ctx.architect.jira_ticket_key
        slack_mock["action"] = ctx.architect.action

    return AlertProcessingResult(
        alert_id=alert_id,
        steps=steps,
        final_status=status,
        slack_mock=slack_mock,
    )

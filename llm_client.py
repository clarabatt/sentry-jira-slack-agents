import json
import google.generativeai as genai
from config import get_settings
from models import GatekeeperDecision, DiplomatAction

_client = None


def get_client():
    global _client
    if _client is None:
        settings = get_settings()
        genai.configure(api_key=settings.gemini_api_key)
        _client = genai.GenerativeModel("gemini-2.5-flash")
    return _client


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


async def gatekeeper_classify(alert: dict, existing_ticket_id: str | None) -> GatekeeperDecision:
    client = get_client()

    existing_info = (
        f"A Jira ticket already exists for this issue: {existing_ticket_id}"
        if existing_ticket_id
        else "No existing Jira ticket found for this issue."
    )

    prompt = f"""You are a Sentry triage Gatekeeper. Analyze this alert and classify it.

ALERT:
Title: {alert['title']}
URL Path: {alert['url_path']}
Stack Trace: {alert['stack_trace']}
Environment: {alert['environment']}
Times Seen: {alert['times_seen']}
Level: {alert['level']}

{existing_info}

Classify this alert as one of:
- "duplicate": ticket already exists in Jira
- "noise": infra/deploy issue, not actionable (e.g. RemoteProtocolError during deploy, connection resets)
- "high_priority": critical production issue (ForeignKeyViolation on critical tables, DiskFullError, 500 spikes)
- "valid_bug": real bug that needs a ticket

Respond ONLY with valid JSON (no markdown, no explanation):
{{
  "classification": "valid_bug|noise|duplicate|high_priority",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation in 1-2 sentences",
  "is_high_priority": true|false
}}"""

    response = client.generate_content(prompt)
    data = _parse_json(response.text)
    data["existing_ticket_id"] = existing_ticket_id
    return GatekeeperDecision(**data)


async def diplomat_compose(action: str, team: str, ticket_key: str | None, reasoning: str, alert_title: str) -> DiplomatAction:
    client = get_client()

    prompt = f"""You are the Diplomat agent in a Sentry triage system. Compose a concise Slack thread message.

ACTION TAKEN: {action}
TEAM ASSIGNED: {team}
JIRA TICKET: {ticket_key or 'N/A'}
REASONING: {reasoning}
ALERT: {alert_title}

Rules:
- Be concise and technical
- If action is "create_ticket": emoji is "🎫", mention team and ticket
- If action is "archive": emoji is "🔇", explain it's already tracked
- If action is "resolve": emoji is "✅", explain why it's noise
- If action is "escalate": emoji is "🚨", be urgent

Respond ONLY with valid JSON:
{{
  "emoji": "single emoji",
  "thread_message": "slack thread message (max 2 sentences)",
  "escalation_message": "urgent message if high priority, else null",
  "escalation_targets": ["@handle1"] or []
}}"""

    response = client.generate_content(prompt)
    data = _parse_json(response.text)
    return DiplomatAction(**data)

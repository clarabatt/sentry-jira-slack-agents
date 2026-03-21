import json
import re
import google.generativeai as genai
from config import get_settings
from models import GatekeeperDecision, DiplomatAction
from json_utils import extract_json_payload

_client = None


def get_client():
    global _client
    if _client is None:
        settings = get_settings()
        genai.configure(api_key=settings.gemini_api_key)
        _client = genai.GenerativeModel("gemini-2.5-flash")
    return _client


def _parse_json(text: str) -> dict:
    return extract_json_payload(text)


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

    response = await client.generate_content_async(prompt)
    data = _parse_json(response.text)
    return DiplomatAction(**data)

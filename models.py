from pydantic import BaseModel
from typing import Optional
from enum import Enum

class Classification(str, Enum):
    duplicate = "duplicate"
    valid_bug = "valid_bug"
    noise = "noise"
    high_priority = "high_priority"
    error = "gatekeeper_error"

class AlertScenario(str, Enum):
    valid_bug = "valid_bug"
    high_priority = "high_priority"
    noise = "noise"
    duplicate = "duplicate"

class Action(str, Enum):
    create_ticket = "create_ticket"
    archive = "archive"
    resolve = "resolve"
    manual_triage = "manual_triage"
    escalate = "escalate"
    system_failure = "system_failure"

class Priority(str, Enum):
    highest = "Highest"
    high = "High"
    medium = "Medium"
    low = "Low"
    unpriorized = "Unpriorized"

class ProcessingStatus(str, Enum):
    running = "running"
    done = "done"
    skipped = "skipped"
    error = "error"


class SentryAlert(BaseModel):
    id: str
    title: str
    culprit: str
    level: str
    status: str
    url_path: str
    stack_trace: str
    environment: str
    times_seen: int
    first_seen: str
    last_seen: str
    scenario: AlertScenario


class JiraTicket(BaseModel):
    id: str
    key: str
    summary: str
    status: str
    priority: Priority
    assignee: Optional[str]
    sentry_issue_id: Optional[str]
    url_path: str
    created_at: str


class GatekeeperDecision(BaseModel):
    classification: Classification
    confidence: float            # 0.0 - 1.0
    reasoning: str
    is_high_priority: bool
    existing_ticket_id: Optional[str] = None


class ArchitectDecision(BaseModel):
    team: str
    team_slack_handle: str
    leads: list[str]
    action: Action
    jira_ticket_key: Optional[str] = None
    triage_owner: str


class DiplomatAction(BaseModel):
    emoji: str
    thread_message: str
    escalation_message: Optional[str] = None
    escalation_targets: list[str] = []


class AgentContext(BaseModel):
    alert: SentryAlert
    gatekeeper: Optional[GatekeeperDecision] = None
    architect: Optional[ArchitectDecision] = None
    diplomat: Optional[DiplomatAction] = None


class ProcessingStep(BaseModel):
    agent: str
    status: ProcessingStatus
    result: Optional[dict] = None


class AlertProcessingResult(BaseModel):
    alert_id: str
    steps: list[ProcessingStep]
    final_status: str
    slack_mock: dict

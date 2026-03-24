import json
import logging
import sys
from pathlib import Path

import google.generativeai as genai
from google.generativeai.types import Tool, FunctionDeclaration
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from models import Classification
from text_utils import get_response_text, clean_response_text
from config import get_settings

logger = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash"
settings = get_settings()

genai.configure(api_key=settings.gemini_api_key)
_gemini_client = genai.GenerativeModel(MODEL)


# ── Connect to the Jira MCP server ─────────────────────────────────────────

async def get_jira_session():
    cmd = sys.executable
    target = Path(__file__).resolve().parent / "mcp_jira.py"
    logger.info("get_jira_session", extra={"cmd": cmd, "target": str(target), "exists": target.exists()})
    server_params = StdioServerParameters(command=cmd, args=[str(target)])
    return stdio_client(server_params)


# ── Gatekeeper: classify + dedup via MCP ───────────────────────────────────

async def run_gatekeeper(alert: dict) -> dict:
    async with await get_jira_session() as (read, write):
        try:
            async with ClientSession(read, write) as session:
                logger.info("MCP session initialized")
                await session.initialize()
                logger.info("MCP initialize done")

                # Fetch available tools from the MCP server
                tools_result = await session.list_tools()
                logger.info("MCP list_tools done", extra={"tool_count": len(tools_result.tools)})
                tools = Tool(
                    function_declarations=[
                        FunctionDeclaration(
                            name=t.name,
                            description=t.description,
                            parameters=t.inputSchema
                        )
                        for t in tools_result.tools
                    ]
                )

                # Initialize Gemini client and craft the prompt
                genai.configure(api_key=settings.gemini_api_key)
                client = genai.GenerativeModel(MODEL)
                
                prompt = f"""You are a Sentry triage Gatekeeper. Your job is to classify incoming alerts accurately.

                ALERT:
                Title:       {alert['title']}
                URL Path:    {alert['url_path']}
                Stack Trace: {alert['stack_trace']}
                Environment: {alert['environment']}
                Times Seen:  {alert['times_seen']}
                Level:       {alert['level']}

                STEP 1 — DEDUPLICATION
                Call search_jira_issues with the sentry_issue_id AND the url_path.
                You will receive a list of existing Jira tickets. An alert is a DUPLICATE only if ALL of the following are true:
                - The sentry_issue_id matches exactly, OR
                - The error TYPE is identical (e.g. both are AttributeError, not just "both are null errors")
                    AND the failing function/method name matches (compare stack trace line by line)
                    AND the url_path matches exactly (e.g. /metrics/v1/metrics/{{id}} ≠ /metrics/v1/metrics)
                    AND the root variable or property causing the error is the same
                    (e.g. reading 'metric_id' ≠ reading 'taxonomy_id', even if both are TypeError on null)

                These are NOT duplicates — do not mark them as duplicate even if they look similar:
                - Same error class (TypeError, AttributeError) but different property names
                - Same error class but different endpoints
                - Same endpoint but different stack trace locations (different line, different function)
                - A generic "null is not an object" vs a specific "Cannot read properties of null (reading 'X')"

                STEP 2 — CLASSIFICATION
                After checking for duplicates, classify the alert as exactly one of:

                "duplicate"     → A ticket already exists for this exact issue (per rules above)
                "noise"         → Infra or transient issue, not actionable. Examples:
                                    - RemoteProtocolError, connection resets, peer closed connection
                                    - Errors that correlate with a deploy window #TODO
                                    - Health check failures, temporary timeouts on non-critical paths
                "high_priority" → Critical production issue requiring immediate attention. Examples:
                                    - ForeignKeyViolationError or IntegrityError on core tables
                                    - DiskFullError, out of memory
                                    - Sudden spike (times_seen > 200 in short window)
                                    - Any error on an authentication or billing path
                "valid_bug"     → A real, actionable bug that needs a Jira ticket. Default to this
                                    when unsure between valid_bug and noise.

                STEP 3 — CONFIDENCE SCORING
                Score your confidence from 0.0 to 1.0:
                1.0 — sentry_issue_id matched exactly in Jira (certain duplicate)
                0.9 — all three signals match: error type + function name + endpoint
                0.7 — two signals match but one is ambiguous
                0.5 — error type matches but endpoint or stack frame differs
                < 0.5 — only superficial similarity (same error class, nothing else)

                Respond ONLY with valid JSON, no markdown:
                {{
                "classification": "duplicate | noise | valid_bug | high_priority",
                "confidence": 0.0-1.0,
                "reasoning": "Cite specific evidence: which stack frame matched, which property name, which endpoint. Max 3 sentences.",
                "is_high_priority": true | false,
                "existing_ticket_id": "NF-XXXXX or null"
                }}"""

                response = await client.generate_content_async(
                    prompt,
                    tools=tools,  # Gemini sees the MCP tools as function declarations
                )

                # If Gemini decided to call a tool, execute it via MCP
                function_call_handled = False
                for part in response.parts:
                    if hasattr(part, "function_call"):
                        function_call_handled = True
                        fc = part.function_call
                        tool_result = await session.call_tool(
                            fc.name,
                            arguments=dict(fc.args),
                        )
                        tool_text = tool_result.content[0].text
                        # Feed the tool result back to Gemini for final classification
                        followup_prompt = "\n".join([
                            prompt,
                            "Tool output:",
                            tool_text,
                            "Now give me the final JSON classification. Output only valid JSON with no additional text."
                        ])

                        followup = await client.generate_content_async(followup_prompt)
                        logger.debug("Follow-up response object", extra={"followup": repr(followup)})
                        followup_text = get_response_text(followup)
                        logger.debug("Extracted followup_text", extra={"followup_text": repr(followup_text)})

                        followup_text = clean_response_text(followup_text)

                        if not followup_text:
                            raise RuntimeError(f"empty followup response: {followup}")
                        return json.loads(followup_text)

                if not function_call_handled:
                    # Gemini answered directly without calling a tool — use safe accessor
                    direct_text = get_response_text(response)
                    if not direct_text:
                        logger.error("Gemini returned empty text candidate", extra={"response": repr(response)})
                        return {
                            "classification": Classification.error,
                            "confidence": 0.0,
                            "reasoning": "Gemini generate_content_async returned an empty model content; cannot parse response.",
                            "is_high_priority": False,
                            "existing_ticket_id": None,
                        }
                    return json.loads(clean_response_text(direct_text))
        except* Exception as e:
            logger.error("run_gatekeeper error", exc_info=True)
            raise
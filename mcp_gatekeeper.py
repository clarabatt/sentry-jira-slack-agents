import json
import sys
from pathlib import Path

import google.generativeai as genai
from google.generativeai.types import Tool, FunctionDeclaration
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from config import get_settings

MODEL = "gemini-2.5-flash"
settings = get_settings()

def get_response_text(gen_response):
    if getattr(gen_response, "text", None):
        return gen_response.text.strip()

    for candidate in getattr(gen_response, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        if content is None:
            continue

        if isinstance(content, str):
            return content.strip()

        parts = getattr(content, "parts", None) or []
        for part in parts:
            if isinstance(part, str):
                return part.strip()
            if getattr(part, "text", None):
                return part.text.strip()

    return ""

def clean_response_text(text):
    if text.startswith('```json\n') and text.endswith('\n```'):
        return text[8:-4] 
    return text.strip()

# ── Connect to the Jira MCP server ─────────────────────────────────────────

async def get_jira_session():
    cmd = sys.executable
    target = Path(__file__).resolve().parent / "mcp_jira.py"
    print("get_jira_session:", cmd, target, "exists:", target.exists())
    server_params = StdioServerParameters(command=cmd, args=[str(target)])
    return stdio_client(server_params)


# ── Gatekeeper: classify + dedup via MCP ───────────────────────────────────

async def run_gatekeeper(alert: dict) -> dict:
    async with await get_jira_session() as (read, write):
        try:
            async with ClientSession(read, write) as session:
                print("MCP session initialized")
                await session.initialize()
                print("MCP initialize done")

                # Fetch available tools from the MCP server
                tools_result = await session.list_tools()
                print("MCP list_tools done, tools:", len(tools_result.tools))
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
                
                prompt = f"""
                You are a Sentry triage Gatekeeper. Analyze this alert and classify it.

                Alert:
                    Title: {alert['title']}
                    URL Path: {alert['url_path']}
                    Stack Trace: {alert['stack_trace']}
                    Environment: {alert['environment']}
                    Times Seen: {alert['times_seen']}
                    Level: {alert['level']}

                First, call search_jira_issues to check if this alert is already tracked.
                Then Classify this alert as one of:
                - "duplicate": ticket already exists in Jira
                - "noise": infra/deploy issue, not actionable (e.g. RemoteProtocolError during deploy, connection resets)
                - "high_priority": critical production issue (ForeignKeyViolation on critical tables, DiskFullError, 500 spikes)
                - "valid_bug": real bug that needs a ticket

                Respond in JSON:
                {{
                "classification": "...",
                "confidence": 0.0-1.0,
                "reasoning": "...",
                "is_high_priority": true|false,
                "existing_ticket_id": "NF-XXXXX or null"
                }}
                """

                response = client.generate_content(
                    prompt,
                    tools=tools,  # Gemini sees the MCP tools as function declarations
                )

                # If Gemini decided to call a tool, execute it via MCP
                for part in response.parts:
                    if hasattr(part, "function_call"):
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

                        followup = client.generate_content(followup_prompt)
                        print("Follow-up response object:", followup)
                        followup_text = get_response_text(followup)
                        print("Extracted followup_text:", repr(followup_text))

                        followup_text = clean_response_text(followup_text)

                        if not followup_text:
                            raise RuntimeError(f"empty followup response: {followup}")
                        return json.loads(followup_text)

                # Gemini answered directly without calling a tool
                return json.loads(response.text.strip())
        except* Exception as e:
            print("run_gatekeeper error:", e)
            raise
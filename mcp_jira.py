import json
from pathlib import Path
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

app = Server("jira-mcp")

DATA_FILE = Path(__file__).resolve().parent / "data" / "jira_tickets.json"
print("mcp_jira DATA_FILE:", DATA_FILE, "exists:", DATA_FILE.exists())

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_jira_issues",
            description="Search Jira tickets by Sentry issue ID or URL path",
            inputSchema={
                "type": "object",
                "properties": {
                    "sentry_issue_id": {"type": "string"},
                    "url_path": {"type": "string"},
                },
            },
        ),
        Tool(
            name="create_jira_ticket",
            description="Create a new Jira ticket prefixed with [Sentry]",
            inputSchema={
                "type": "object",
                "required": ["summary", "priority", "sentry_issue_id"],
                "properties": {
                    "summary": {"type": "string"},
                    "priority": {"type": "string"},
                    "sentry_issue_id": {"type": "string"},
                    "url_path": {"type": "string"},
                },
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        tickets = json.loads(DATA_FILE.read_text())
    except Exception as e:
        print("mcp_jira load data error:", e)
        raise

    if name == "search_jira_issues":
        results = [
            t for t in tickets
            if t.get("sentry_issue_id") == arguments.get("sentry_issue_id")
            or (arguments.get("url_path") and t.get("url_path") in arguments["url_path"])
        ]
        return [TextContent(type="text", text=json.dumps(results))]

    if name == "create_jira_ticket":
        ticket = {
            "id": f"NF-{21922 + len(tickets)}",
            "key": f"NF-{21922 + len(tickets)}",
            "summary": f"[Sentry] {arguments['summary']}",
            "priority": arguments["priority"],
            "status": "GROOMING",
            "sentry_issue_id": arguments["sentry_issue_id"],
            "url_path": arguments.get("url_path", ""),
            "assignee": None,
            "created_at": "2026-03-20T09:30:00Z",
        }
        tickets.append(ticket)
        DATA_FILE.write_text(json.dumps(tickets, indent=2))
        return [TextContent(type="text", text=json.dumps(ticket))]


async def main():
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
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

def _normalize_path(path: str) -> str:
    """Replace UUIDs, numeric IDs and slugs with {id} placeholder."""
    import re
    if not path:
        return ""
    # UUIDs
    path = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '{id}', path)
    # Numeric IDs
    path = re.sub(r'/\d+', '/{id}', path)
    # Alphanumeric slugs that look like IDs (e.g. abc-123, NF-21910)
    path = re.sub(r'/[a-zA-Z0-9]+-[a-zA-Z0-9]+', '/{id}', path)
    return path.rstrip('/')


def _paths_match(stored: str, incoming: str) -> bool:
    """Match normalized paths — must be the same endpoint, not just overlapping."""
    return _normalize_path(stored) == _normalize_path(incoming)

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        tickets = json.loads(DATA_FILE.read_text())
    except Exception as e:
        print("mcp_jira load data error:", e)
        raise

    if name == "search_jira_issues":
        sentry_id = arguments.get("sentry_issue_id")
        url_path   = arguments.get("url_path")

        results = [
            t for t in tickets
            if (sentry_id and t.get("sentry_issue_id") == sentry_id)
            or (url_path and t.get("url_path") and _paths_match(t["url_path"], url_path))
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
        # For now we just print the new ticket instead of writing to a file
        # DATA_FILE.write_text(json.dumps(tickets, indent=2))
        return [TextContent(type="text", text=json.dumps(ticket))]


async def main():
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
import json
from pathlib import Path
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from mock_db import create_jira_ticket, load_jira_tickets

app = Server("jira-mcp")

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
    tickets = load_jira_tickets()

    if name == "search_jira_issues":
        sentry_id = arguments.get("sentry_issue_id")
        url_path = arguments.get("url_path")

        results = [
            t for t in tickets
            if (sentry_id and t.sentry_issue_id == sentry_id)
            or (url_path and t.url_path and _paths_match(t.url_path, url_path))
        ]
        return [TextContent(type="text", text=json.dumps([r.model_dump() for r in results]))]

    if name == "create_jira_ticket":
        ticket = create_jira_ticket(
            summary=arguments["summary"],
            priority=arguments["priority"],
            url_path=arguments.get("url_path", ""),
            sentry_id=arguments["sentry_issue_id"],
        )
        return [TextContent(type="text", text=json.dumps(ticket.model_dump()))]


async def main():
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
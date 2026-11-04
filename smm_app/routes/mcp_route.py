"""
MCP Discovery and Metadata Endpoint for See My Mind CRM
"""
from fastapi import APIRouter
from smm_app.mcp.server import mcp

router = APIRouter(prefix="/mcp", tags=["mcp"])


@router.get("/info")
def mcp_server_info():
    """Returns MCP connection instructions, available tools, and configuration snippets."""
    return {
        "name": mcp.name,
        "protocol": "Model Context Protocol (MCP)",
        "version": "2.0",
        "description": "Standardized MCP tools for See My Mind Education CRM intelligence and outreach drafting.",
        "connection_command": "python -m smm_app.mcp.server",
        "mcp_config_snippet": {
            "mcpServers": {
                "seemymind": {
                    "command": "python",
                    "args": ["-m", "smm_app.mcp.server"],
                    "cwd": "c:\\Apps\\LeadGen\\halo-lead-agent",
                }
            }
        },
        "tools": [
            {
                "name": "search_schools",
                "description": "Search schools by name, postcode, or multi-academy trust",
            },
            {
                "name": "get_school_context",
                "description": "Retrieve full SEND intelligence, Ofsted quote, scores, and contacts for a school",
            },
            {
                "name": "get_school_activities",
                "description": "Retrieve all logged calls, meeting notes, CRM activities, and open follow-ups",
            },
            {
                "name": "log_school_activity",
                "description": "Log a phone call, meeting, email, demo, or discussion note to the school timeline",
            },
            {
                "name": "draft_school_outreach",
                "description": "On-demand outreach drafting (SENCO email, Head email, letter) factoring in CRM notes",
            },
            {
                "name": "list_schools",
                "description": "List target schools filtered by pipeline stage or priority tier",
            },
        ],
    }

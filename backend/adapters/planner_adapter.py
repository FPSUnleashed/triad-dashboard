from __future__ import annotations
import re
import os
from .agent0_client import send_fresh_chat
from .notion_client import NotionClient


def extract_notion_urls(text: str) -> list[str]:
    """Extract Notion URLs from text."""
    pattern = r'https?://(?:www\.)?notion\.so/(?:[^/]+-)?([a-f0-9]{32}|[a-f0-9]{8}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{12})'
    return list(set(re.findall(pattern, text)))


def fetch_notion_content(urls: list[str]) -> str:
    """Fetch content from Notion URLs."""
    api_key = os.environ.get("NOTION_API_KEY")
    if not api_key:
        return "[NOTION_API_KEY not set - cannot fetch Notion pages]"

    client = NotionClient(api_key)
    contents = []

    for page_id in urls:
        try:
            # Normalize page ID if needed
            if len(page_id) == 32:
                page_id = f"{page_id[:8]}-{page_id[8:12]}-{page_id[12:16]}-{page_id[16:20]}-{page_id[20:]}"

            page_data = client.get_page_with_content(page_id)
            contents.append(f"\n=== NOTION: {page_data['title']} ===\n{page_data['content']}\n")
        except Exception as e:
            contents.append(f"[Error fetching Notion page {page_id}: {e}]")

    return "\n".join(contents)


def build_planner_input(planner_prompt: str, run_goal: str, global_context: str, last_done_thing: str) -> str:
    """Build planner input, fetching any Notion URLs in global_context."""

    # Check for Notion URLs in global context and fetch their content
    notion_urls = extract_notion_urls(global_context)
    notion_content = ""
    if notion_urls:
        notion_content = fetch_notion_content(notion_urls)

    parts = [
        "[PLANNER PROMPT]",
        planner_prompt,
        "",
        "[GOAL]",
        run_goal or "(No specific goal set - proceed autonomously)",
        "",
    ]

    if notion_content:
        parts.extend([
            "[NOTION PAGES - LIVE FETCH]",
            notion_content,
            "",
        ])

    parts.extend([
        "[GLOBAL CONTEXT]",
        global_context,
        "",
        "[LAST DONE THING / REVIEW REPORT]",
        last_done_thing or "(Fresh start - no previous cycle)",
        "",
        "Return a worker-ready task packet following the strict output format."
    ])

    return "\n".join(parts)


async def run_planner(input_payload: str) -> dict:
    return await send_fresh_chat(input_payload)

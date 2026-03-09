from __future__ import annotations
import re
import os
from .agent0_client import send_fresh_chat
from .notion_client import NotionClient


# Required Notion pages to always fetch for planner context
REQUIRED_NOTION_PAGES = [
    {
        "id": "3086fd9c2bc281439cf6dee9b6362153",
        "name": "Products",
        "url": "https://www.notion.so/Products-3086fd9c2bc281439cf6dee9b6362153"
    },
    {
        "id": "3066fd9c2bc281739334fbc74491b5a1",
        "name": "FPS Unleashed (Business)",
        "url": "https://www.notion.so/FPS-Unleashed-3066fd9c2bc281739334fbc74491b5a1"
    }
]


def normalize_page_id(page_id: str) -> str:
    """Normalize a 32-char page ID to UUID format."""
    clean = page_id.replace("-", "")
    if len(clean) == 32:
        return f"{clean[:8]}-{clean[8:12]}-{clean[12:16]}-{clean[16:20]}-{clean[20:]}"
    return page_id


def extract_notion_urls(text: str) -> list[str]:
    """Extract Notion page IDs from text."""
    pattern = r'https?://(?:www\.)?notion\.so/(?:[^/]+-)?([a-f0-9]{32}|[a-f0-9]{8}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{12})'
    return list(set(re.findall(pattern, text)))


def fetch_notion_content(page_ids: list[str]) -> str:
    """Fetch content from Notion page IDs."""
    api_key = os.environ.get("NOTION_API_KEY")
    if not api_key:
        return "[NOTION_API_KEY not set - cannot fetch Notion pages]"

    client = NotionClient(api_key)
    contents = []

    for page_id in page_ids:
        try:
            normalized_id = normalize_page_id(page_id)
            page_data = client.get_page_with_content(normalized_id)
            contents.append(f"\n=== NOTION: {page_data['title']} ===\n{page_data['content']}\n")
        except Exception as e:
            contents.append(f"[Error fetching Notion page {page_id}: {e}]")

    return "\n".join(contents)


def build_planner_input(planner_prompt: str, run_goal: str, global_context: str, last_done_thing: str, planner_state: str = '') -> str:
    """Build planner input, always fetching required Notion pages + any in global_context."""

    # Always include required Notion pages
    required_ids = [p["id"] for p in REQUIRED_NOTION_PAGES]
    
    # Also check for additional Notion URLs in global context
    extra_ids = extract_notion_urls(global_context)
    
    # Combine and dedupe
    all_ids = list(set(required_ids + extra_ids))
    
    # Fetch all Notion content
    notion_content = ""
    if all_ids:
        notion_content = fetch_notion_content(all_ids)

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
            "[NOTION PAGES - REQUIRED CONTEXT]",
            notion_content,
            "",
        ])

    parts.extend([
        "[GLOBAL CONTEXT]",
        global_context,
        "",
    ])

    if planner_state:
        parts.extend([
            planner_state,
            "",
        ])

    parts.extend([
        "[LAST DONE THING / REVIEW REPORT]",
        last_done_thing or "(Fresh start - no previous cycle)",
        "",
        "Treat the RUN STATE block as canonical. If RUN_MODE is IN_PROGRESS, continue or revise the stored task list instead of acting like this is a blank slate.",
        "Return a worker-ready task packet following the strict output format."
    ])

    return "\n".join(parts)


async def run_planner(input_payload: str) -> dict:
    return await send_fresh_chat(input_payload)

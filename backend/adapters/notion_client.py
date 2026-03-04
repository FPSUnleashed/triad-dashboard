"""Notion API client for fetching page content."""
import os
import re
import requests
from typing import Optional, Dict, List, Any


class NotionClient:
    """Client for interacting with Notion API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("NOTION_API_KEY")
        if not self.api_key:
            raise ValueError("NOTION_API_KEY not set")
        self.base_url = "https://api.notion.com/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }

    def search_pages(self, query: str = "", page_size: int = 10) -> List[Dict[str, Any]]:
        """Search for pages matching query."""
        response = requests.post(
            f"{self.base_url}/search",
            headers=self.headers,
            json={
                "query": query,
                "filter": {"property": "object", "value": "page"},
                "page_size": page_size
            }
        )
        response.raise_for_status()
        return response.json().get("results", [])

    def get_page(self, page_id: str) -> Dict[str, Any]:
        """Get page properties."""
        response = requests.get(
            f"{self.base_url}/pages/{page_id}",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def get_page_content(self, page_id: str, max_blocks: int = 100) -> str:
        """Get page content as plain text."""
        blocks = []
        has_more = True
        start_cursor = None

        while has_more and len(blocks) < max_blocks:
            params = {"page_size": min(50, max_blocks - len(blocks))}
            if start_cursor:
                params["start_cursor"] = start_cursor

            response = requests.get(
                f"{self.base_url}/blocks/{page_id}/children",
                headers=self.headers,
                params=params
            )
            response.raise_for_status()
            data = response.json()
            blocks.extend(data.get("results", []))
            has_more = data.get("has_more", False)
            start_cursor = data.get("next_cursor")

        # Convert blocks to text
        text_parts = []
        for block in blocks[:max_blocks]:
            block_type = block.get("type")
            content = block.get(block_type, {})

            if "rich_text" in content:
                text = "".join([t["plain_text"] for t in content["rich_text"]])
                if text.strip():
                    if block_type == "heading_1":
                        text_parts.append("# " + text)
                    elif block_type == "heading_2":
                        text_parts.append("## " + text)
                    elif block_type == "heading_3":
                        text_parts.append("### " + text)
                    elif block_type == "bulleted_list_item":
                        text_parts.append("- " + text)
                    elif block_type == "to_do":
                        checked = "[x]" if content.get("checked") else "[ ]"
                        text_parts.append(checked + " " + text)
                    else:
                        text_parts.append(text)

        return "\n".join(text_parts)

    def get_page_with_content(self, page_id: str) -> Dict[str, Any]:
        """Get page properties and content."""
        page = self.get_page(page_id)
        content = self.get_page_content(page_id)

        # Extract title
        title = ""
        for key, val in page.get("properties", {}).items():
            if val.get("type") == "title" and val.get("title"):
                title = val["title"][0]["plain_text"]
                break

        return {
            "id": page_id,
            "title": title,
            "url": f"https://notion.so/{page_id.replace(chr(45), chr(45))}",
            "content": content
        }

    def fetch_page_by_url(self, url: str) -> Dict[str, Any]:
        """Fetch page content from a Notion URL."""
        # Extract page ID from URL
        match = re.search(r"([a-f0-9]{32}|[a-f0-9]{8}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{12})", url)
        if not match:
            raise ValueError(f"Could not extract page ID from URL: {url}")

        page_id = match.group(1)
        # Normalize to UUID format
        if len(page_id) == 32:
            page_id = f"{page_id[:8]}-{page_id[8:12]}-{page_id[12:16]}-{page_id[16:20]}-{page_id[20:]}"

        return self.get_page_with_content(page_id)

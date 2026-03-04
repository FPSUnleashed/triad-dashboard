from __future__ import annotations

import re

from .agent0_client import send_fresh_chat


VERDICTS = ("APPROVE", "REQUEST_CHANGES", "BLOCKED_INFRA")


def build_reviewer_input(reviewer_inject_prompt: str, delivery_packet: str) -> str:
    return (
        "[REVIEWER INJECT PROMPT]\n"
        f"{reviewer_inject_prompt}\n\n"
        "[WORKER DELIVERY]\n"
        f"{delivery_packet}\n\n"
        "Return only:\n"
        "- Verdict: APPROVE | REQUEST_CHANGES | BLOCKED_INFRA\n"
        "- Findings\n"
        "- Evidence references\n"
        "- Required next action\n"
    )


def parse_verdict(text: str) -> str:
    upper = text.upper()
    for v in VERDICTS:
        if re.search(rf"\b{v}\b", upper):
            return v
    return "REQUEST_CHANGES"


async def run_reviewer(input_payload: str) -> dict:
    return await send_fresh_chat(input_payload)

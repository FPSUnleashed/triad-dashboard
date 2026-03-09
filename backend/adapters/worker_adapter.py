from __future__ import annotations

from .agent0_client import send_chat


def build_worker_input(
    worker_inject_prompt: str,
    task_packet: str,
    workspace_path: str = "",
    review_feedback: str = "",
) -> str:
    parts = [
        "[WORKER INJECT PROMPT]",
        worker_inject_prompt,
        "",
    ]

    if workspace_path:
        parts.extend([
            "[WORKSPACE PROTOCOL - MANDATORY]",
            f"- Your isolated workspace root is: {workspace_path}",
            f"- Do all filesystem work only inside: {workspace_path}",
            f"- Create or reuse the task repository inside: {workspace_path}/repo",
            "- On the first pass for this task, create a fresh repo copy before coding.",
            "- On follow-up passes after reviewer feedback, KEEP using the same workspace and the same repo inside it.",
            "- Put logs, screenshots, test outputs, and build artifacts under this workspace root.",
            "- Do not clean this workspace yourself; the dashboard controls cleanup.",
            "",
        ])

    parts.extend([
        "[PLANNER OUTPUT / TASK PACKET]",
        task_packet,
        "",
    ])

    if review_feedback:
        parts.extend([
            "[REVIEWER FEEDBACK / CHANGE REQUEST]",
            review_feedback,
            "",
            "This is the SAME task in the SAME workspace. Continue from the existing repo state and fix the reviewer findings with evidence.",
            "",
        ])

    parts.append(
        "Execute this task FULLY. Do not defer to humans. Do not stop at ready for review. Return a delivery packet only when ALL acceptance criteria are MET with evidence."
    )
    return "\n".join(parts)


async def run_worker(input_payload: str, context_id: str | None = None) -> dict:
    return await send_chat(input_payload, context_id=context_id)

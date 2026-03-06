from __future__ import annotations

from .agent0_client import send_fresh_chat


def build_worker_input(worker_inject_prompt: str, task_packet: str) -> str:
    return (
        "[WORKER INJECT PROMPT]\n"
        f"{worker_inject_prompt}\n\n"
        "[PLANNER OUTPUT / TASK PACKET]\n"
        f"{task_packet}\n\n"
        "Execute this task FULLY. Do not defer to humans. Do not stop at 'ready for review'. "
        "Return a delivery packet only when ALL acceptance criteria are MET with evidence."
    )


async def run_worker(input_payload: str) -> dict:
    return await send_fresh_chat(input_payload)

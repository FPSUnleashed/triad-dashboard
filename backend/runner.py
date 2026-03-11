from __future__ import annotations
from pathlib import Path

import asyncio
import re

import shutil
from typing import Any

from .adapters.planner_adapter import build_planner_input, run_planner
from .adapters.worker_adapter import build_worker_input, run_worker
from .adapters.reviewer_adapter import build_reviewer_input, parse_verdict, run_reviewer
from .db import execute, fetch_all, fetch_one, insert_and_get_id, json_dumps, utc_now
# Worker workspace base directory
WORKSPACE_BASE = Path(__file__).parent.parent / "tmp" / "worker_runs"
MAX_DEBUG_ITERATIONS = 12  # Max worker↔reviewer debug loop iterations



def extract_last_done_thing(reviewer_output: str, verdict: str) -> str:
    """Extract a summary from reviewer output to use as last_done_thing."""
    if not reviewer_output:
        return ""

    patterns = [
        r"(?:SUMMARY|FINDINGS|RESULT|COMPLETED):\\s*(.+?)(?:\\n|$)",
        r"(?:Verdict|Decision):\\s*(?:APPROVE|REQUEST_CHANGES|BLOCKED_INFRA)\\s*[-:]?\\s*(.+?)(?:\\n\\n|$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, reviewer_output, re.IGNORECASE | re.DOTALL)
        if match:
            extracted = match.group(1).strip()[:500]
            return f"[{verdict}] {extracted}"

    lines = [l.strip() for l in reviewer_output.split("\\n") if l.strip() and len(l.strip()) > 20]
    if lines:
        return f"[{verdict}] {lines[0][:500]}"

    return f"[{verdict}] Reviewer completed"




def _get_worker_workspace_path(run_id: int) -> Path:
    """Get the workspace path for a run's worker."""
    return WORKSPACE_BASE / f'run_{run_id}'


def _create_worker_workspace(run_id: int) -> Path:
    """Create and return the worker workspace for a run."""
    ws = _get_worker_workspace_path(run_id)
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def _clean_worker_workspace(run_id: int) -> bool:
    """Remove the worker workspace for a run. Returns True if cleaned."""
    ws = _get_worker_workspace_path(run_id)
    if ws.exists():
        shutil.rmtree(ws, ignore_errors=True)
        return True
    return False


def _workspace_exists(run_id: int) -> bool:
    """Check if a worker workspace exists."""
    return _get_worker_workspace_path(run_id).exists()

class TriadRunner:
    def __init__(self) -> None:
        self._tasks: dict[int, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self._stop_requests: set[int] = set()
        self._pause_requests: set[int] = set()
        # Safety default: paused to avoid runaway chat creation.
        self._auto_loop_enabled: bool = False

    @property
    def auto_loop_enabled(self) -> bool:
        return self._auto_loop_enabled

    def set_auto_loop_enabled(self, enabled: bool) -> bool:
        self._auto_loop_enabled = bool(enabled)
        return self._auto_loop_enabled

    def is_running(self, run_id: int) -> bool:
        t = self._tasks.get(run_id)
        return bool(t and not t.done())

    def stop(self, run_id: int, reason: str = "Cancelled by user") -> dict[str, Any]:
        """Cancel a run immediately. Marks run/step as cancelled (not failed)."""
        self._stop_requests.add(run_id)
        self._pause_requests.discard(run_id)

        task = self._tasks.get(run_id)
        task_cancelled = False
        if task and not task.done():
            task.cancel()
            task_cancelled = True

        now = utc_now()
        execute(
            """
            UPDATE run_steps
            SET status='cancelled',
                error=COALESCE(error, ?),
                ended_at=COALESCE(ended_at, ?)
            WHERE run_id=? AND status='running'
            """,
            (reason, now, run_id),
        )

        row = fetch_one("SELECT status FROM runs WHERE id=?", (run_id,))
        if row and row.get("status") in ("running", "paused"):
            self._set_run_status(run_id, "cancelled")

        self._event(run_id, "warn", "Run cancelled by user", {"reason": reason, "task_cancelled": task_cancelled})
        return {"task_cancelled": task_cancelled}

    def pause(self, run_id: int, reason: str = "Paused by user") -> dict[str, Any]:
        """Pause run execution. Current running step is paused and can be resumed."""
        self._pause_requests.add(run_id)
        self._stop_requests.discard(run_id)

        task = self._tasks.get(run_id)
        task_cancelled = False
        if task and not task.done():
            task.cancel()
            task_cancelled = True

        now = utc_now()
        execute(
            """
            UPDATE run_steps
            SET status='paused',
                error=COALESCE(error, ?),
                ended_at=COALESCE(ended_at, ?)
            WHERE run_id=? AND status='running'
            """,
            (reason, now, run_id),
        )

        row = fetch_one("SELECT status FROM runs WHERE id=?", (run_id,))
        if row and row.get("status") == "running":
            self._set_run_status(run_id, "paused")

        self._event(run_id, "info", "Run paused by user", {"reason": reason, "task_cancelled": task_cancelled})
        return {"task_cancelled": task_cancelled}

    async def resume(self, run_id: int) -> dict[str, Any]:
        row = fetch_one("SELECT status FROM runs WHERE id=?", (run_id,))
        if not row:
            raise RuntimeError("run not found")
        if self.is_running(run_id):
            raise RuntimeError("run is already running")
        if row.get("status") != "paused":
            raise RuntimeError("only paused runs can be resumed")

        start_step = self._determine_resume_step(run_id)
        self._pause_requests.discard(run_id)
        self._stop_requests.discard(run_id)
        self._set_run_status(run_id, "running")
        self._event(run_id, "info", "Run resumed", {"start_step": start_step})
        await self.start(run_id, start_step)
        return {"start_step": start_step}

    def _determine_resume_step(self, run_id: int) -> str:
        planner_passed = fetch_one(
            "SELECT 1 AS ok FROM run_steps WHERE run_id=? AND step_name='planner' AND status='passed' ORDER BY id DESC LIMIT 1",
            (run_id,),
        )
        if not planner_passed:
            return "planner"

        worker_passed = fetch_one(
            "SELECT 1 AS ok FROM run_steps WHERE run_id=? AND step_name='worker' AND status='passed' ORDER BY id DESC LIMIT 1",
            (run_id,),
        )
        if not worker_passed:
            return "worker"

        return "reviewer"

    async def start(self, run_id: int, start_step: str = "planner") -> None:
        async with self._lock:
            if self.is_running(run_id):
                raise RuntimeError(f"Run {run_id} is already running")
            self._stop_requests.discard(run_id)
            self._pause_requests.discard(run_id)
            task = asyncio.create_task(self._execute(run_id, start_step))
            self._tasks[run_id] = task

    async def _execute(self, run_id: int, start_step: str) -> None:
        try:
            await self._execute_pipeline(run_id, start_step)
        finally:
            current = asyncio.current_task()
            if self._tasks.get(run_id) is current:
                self._tasks.pop(run_id, None)
            self._stop_requests.discard(run_id)
            self._pause_requests.discard(run_id)

    def _check_stop(self, run_id: int) -> None:
        if run_id in self._stop_requests:
            raise asyncio.CancelledError("Run stop requested")
        if run_id in self._pause_requests:
            raise asyncio.CancelledError("Run pause requested")

    def _event(self, run_id: int, level: str, message: str, meta: dict[str, Any] | None = None) -> None:
        execute(
            "INSERT INTO run_events(run_id, level, message, meta, created_at) VALUES(?,?,?,?,?)",
            (run_id, level, message, json_dumps(meta or {}), utc_now()),
        )

    def _set_run_status(self, run_id: int, status: str, last_done_thing: str | None = None) -> None:
        if last_done_thing is not None:
            execute(
                "UPDATE runs SET status=?, last_done_thing=?, updated_at=? WHERE id=?",
                (status, last_done_thing, utc_now(), run_id),
            )
        else:
            execute(
                "UPDATE runs SET status=?, updated_at=? WHERE id=?",
                (status, utc_now(), run_id),
            )

    def _next_attempt(self, run_id: int, step_name: str) -> int:
        row = fetch_one(
            "SELECT COALESCE(MAX(attempt), 0) AS max_attempt FROM run_steps WHERE run_id=? AND step_name=?",
            (run_id, step_name),
        )
        return int((row or {}).get("max_attempt", 0)) + 1

    def _start_step(self, run_id: int, step_name: str, input_payload: str) -> int:
        attempt = self._next_attempt(run_id, step_name)
        step_id = insert_and_get_id(
            """
            INSERT INTO run_steps(
                run_id, step_name, attempt, status, input_payload, output_payload, error, agent_context_id, started_at, ended_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (run_id, step_name, attempt, "running", input_payload, None, None, None, utc_now(), None),
        )
        self._event(run_id, "info", f"{step_name} started", {"step_id": step_id, "attempt": attempt})
        return step_id

    def _finish_step(
        self,
        step_id: int,
        status: str,
        output_payload: str | None = None,
        error: str | None = None,
        agent_context_id: str | None = None,
    ) -> None:
        execute(
            """
            UPDATE run_steps
            SET status=?, output_payload=?, error=?, agent_context_id=?, ended_at=?
            WHERE id=?
            """,
            (status, output_payload, error, agent_context_id, utc_now(), step_id),
        )

    def _latest_passed_output(self, run_id: int, step_name: str) -> str:
        row = fetch_one(
            """
            SELECT output_payload
            FROM run_steps
            WHERE run_id=? AND step_name=? AND status='passed'
            ORDER BY attempt DESC, id DESC
            LIMIT 1
            """,
            (run_id, step_name),
        )
        output = (row or {}).get("output_payload")
        if not output:
            raise RuntimeError(f"Missing passed output for prerequisite step: {step_name}")
        return str(output)


    def _get_task_steps(self, run_id: int):
        return fetch_all(
            "SELECT * FROM task_steps WHERE run_id=? ORDER BY position ASC, id ASC",
            (run_id,),
        )

    def _normalize_task_title(self, title: str) -> str:
        return " ".join((title or "").split()).strip().lower()

    def _extract_task_title(self, planner_output: str) -> str:
        if not planner_output:
            return ""
        for raw_line in planner_output.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            upper = line.upper()
            if upper.startswith("TASK_TITLE:"):
                return line.split(":", 1)[1].strip()[:500]
            if upper.startswith("**TASK_TITLE**:"):
                return line.split(":", 1)[1].strip()[:500]
            if line.startswith("# "):
                return line[2:].strip()[:500]
        for raw_line in planner_output.splitlines():
            line = raw_line.strip().lstrip('-* ').strip()
            if line and not line.startswith('[') and ':' not in line[:40]:
                return line[:500]
        return ""

    def _build_planner_state(self, run_id: int) -> str:
        steps = self._get_task_steps(run_id)
        open_steps = [s for s in steps if s["status"] in ("pending", "in_progress", "blocked")]
        done_steps = [s for s in steps if s["status"] == "done"]

        lines = [
            "[RUN STATE]",
            f"RUN_MODE: {'IN_PROGRESS' if steps else 'FRESH'}",
            f"HAS_STORED_TASK_STEPS: {'YES' if steps else 'NO'}",
            f"TOTAL_STORED_TASK_STEPS: {len(steps)}",
            f"OPEN_TASK_STEPS: {len(open_steps)}",
            f"COMPLETED_TASK_STEPS: {len(done_steps)}",
            "",
            "[STORED TASK STEPS]",
        ]

        if steps:
            for step in steps[-20:]:
                lines.append(f"{step['position']}. [{step['status']}] {step['title']}")
        else:
            lines.append("(none)")

        lines.extend([
            "",
            "Planner state rules:",
            "- FRESH means no durable task list exists for this run yet.",
            "- IN_PROGRESS means a durable task list already exists; continue or revise it instead of acting like the run is blank.",
            "- Prefer advancing or repairing open stored tasks before inventing unrelated work.",
        ])
        return "\n".join(lines)

    def _copy_task_steps(self, from_run_id: int, to_run_id: int) -> None:
        steps = self._get_task_steps(from_run_id)
        now = utc_now()
        for step in steps:
            insert_and_get_id(
                """
                INSERT INTO task_steps(run_id, position, title, status, details, created_at, updated_at, completed_at)
                VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    to_run_id,
                    step["position"],
                    step["title"],
                    step["status"],
                    step.get("details", "") or "",
                    now,
                    now,
                    step.get("completed_at"),
                ),
            )

    def _sync_task_state_from_planner(self, run_id: int, planner_output: str) -> None:
        title = self._extract_task_title(planner_output)
        if not title:
            self._event(run_id, "warn", "Planner output missing TASK_TITLE; task_steps not updated")
            return

        normalized = self._normalize_task_title(title)
        now = utc_now()
        steps = self._get_task_steps(run_id)

        execute(
            "UPDATE task_steps SET status='pending', updated_at=? WHERE run_id=? AND status='in_progress'",
            (now, run_id),
        )

        match = next((
            step for step in steps
            if step["status"] in ("pending", "in_progress", "blocked")
            and self._normalize_task_title(str(step.get("title", ""))) == normalized
        ), None)

        if match:
            execute(
                "UPDATE task_steps SET title=?, status='in_progress', details=?, updated_at=?, completed_at=NULL WHERE id=?",
                (title, planner_output, now, match["id"]),
            )
            return

        row = fetch_one(
            "SELECT COALESCE(MAX(position), 0) AS max_position FROM task_steps WHERE run_id=?",
            (run_id,),
        )
        position = int((row or {}).get("max_position", 0)) + 1
        insert_and_get_id(
            """
            INSERT INTO task_steps(run_id, position, title, status, details, created_at, updated_at, completed_at)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (run_id, position, title, 'in_progress', planner_output, now, now, None),
        )

    def _mark_current_task_step(self, run_id: int, status: str) -> None:
        row = fetch_one(
            """
            SELECT id FROM task_steps
            WHERE run_id=? AND status='in_progress'
            ORDER BY position DESC, id DESC
            LIMIT 1
            """,
            (run_id,),
        )
        if not row:
            row = fetch_one(
                """
                SELECT id FROM task_steps
                WHERE run_id=? AND status IN ('pending', 'blocked')
                ORDER BY position DESC, id DESC
                LIMIT 1
                """,
                (run_id,),
            )
        if not row:
            return

        now = utc_now()
        if status == 'done':
            execute(
                "UPDATE task_steps SET status=?, updated_at=?, completed_at=? WHERE id=?",
                (status, now, now, row["id"]),
            )
        else:
            execute(
                "UPDATE task_steps SET status=?, updated_at=?, completed_at=NULL WHERE id=?",
                (status, now, row["id"]),
            )

    async def _start_next_run(
        self,
        from_run_id: int,
        profile_id: int,
        goal: str,
        global_context: str,
        last_done_thing: str,
    ) -> None:
        """Create and start the next run in the loop automatically."""
        try:
            new_run_id = insert_and_get_id(
                """
                INSERT INTO runs(profile_id, goal, global_context, last_done_thing, status, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?)
                """,
                (profile_id, goal, global_context, last_done_thing, "running", utc_now(), utc_now()),
            )
            self._copy_task_steps(from_run_id, new_run_id)
            self._event(new_run_id, "info", "Auto-loop: Created next run", {"from_run_id": from_run_id})

            await asyncio.sleep(1)
            if not self._auto_loop_enabled:
                self._set_run_status(new_run_id, "cancelled")
                self._event(new_run_id, "warn", "Auto-loop paused before start; run not executed")
                return

            await self.start(new_run_id, start_step="planner")
        except Exception as e:
            self._event(from_run_id, "error", "Auto-loop failed to start next run", {"error": str(e)})

    async def _execute_pipeline(self, run_id: int, start_step: str) -> None:
        run = fetch_one("SELECT * FROM runs WHERE id=?", (run_id,))
        if not run:
            return

        profile = fetch_one("SELECT * FROM prompt_profiles WHERE id=?", (run["profile_id"],))
        if not profile:
            self._set_run_status(run_id, "failed")
            self._event(run_id, "error", "Prompt profile not found")
            return

        self._set_run_status(run_id, "running")
        self._event(run_id, "info", "Run pipeline started", {"start_step": start_step})

        current_step_id: int | None = None
        current_step_name: str | None = None

        try:
            self._check_stop(run_id)

            if start_step == "planner":
                planner_state = self._build_planner_state(run_id)
                planner_input = build_planner_input(
                    planner_prompt=profile["planner_prompt"],
                    run_goal=run["goal"],
                    global_context=run.get("global_context", "") or "",
                    last_done_thing=run.get("last_done_thing", "") or "",
                    planner_state=planner_state,
                )
                current_step_name = "planner"
                current_step_id = self._start_step(run_id, "planner", planner_input)
                planner_resp = await run_planner(planner_input)
                planner_output = str(planner_resp.get("response", ""))
                self._finish_step(
                    current_step_id,
                    status="passed",
                    output_payload=planner_output,
                    agent_context_id=str(planner_resp.get("context_id", "")),
                )
                self._sync_task_state_from_planner(run_id, planner_output)
                self._event(run_id, "info", "planner passed")
                current_step_id = None
                current_step_name = None
            else:
                planner_output = self._latest_passed_output(run_id, "planner")

            self._check_stop(run_id)

            if start_step in ("planner", "worker"):
                # Create workspace for worker
                ws_path = _get_worker_workspace_path(run_id)
                ws_path.mkdir(parents=True, exist_ok=True)
                workspace_str = str(ws_path)
                self._event(run_id, "info", "Worker workspace created", {"path": workspace_str})

                # Track debug loop state
                debug_iterations = 0
                worker_context_id = None
                reviewer_context_id = None
                worker_output = None
                reviewer_output = None
                verdict = None

                while debug_iterations < MAX_DEBUG_ITERATIONS:
                    debug_iterations += 1
                    self._event(run_id, "info", f"Debug iteration {debug_iterations}/{MAX_DEBUG_ITERATIONS}")

                    # Build worker input with workspace path and review feedback if any
                    review_feedback = reviewer_output if reviewer_output and verdict == "REQUEST_CHANGES" else ""
                    worker_input = build_worker_input(
                        worker_inject_prompt=profile["worker_inject_prompt"],
                        task_packet=planner_output,
                        workspace_path=workspace_str,
                        review_feedback=review_feedback,
                    )
                    current_step_name = "worker"
                    current_step_id = self._start_step(run_id, "worker", worker_input)
                    worker_resp = await run_worker(worker_input, context_id=worker_context_id)
                    worker_output = str(worker_resp.get("response", ""))
                    worker_context_id = str(worker_resp.get("context_id", "")) or worker_context_id
                    self._finish_step(
                        current_step_id,
                        status="passed",
                        output_payload=worker_output,
                        agent_context_id=worker_context_id,
                    )
                    self._event(run_id, "info", "worker passed", {"iteration": debug_iterations})
                    current_step_id = None
                    current_step_name = None

                    self._check_stop(run_id)

                    # Run reviewer
                    reviewer_input = build_reviewer_input(
                        reviewer_inject_prompt=profile["reviewer_inject_prompt"],
                        delivery_packet=worker_output,
                        planner_task=planner_output,
                    )
                    current_step_name = "reviewer"
                    current_step_id = self._start_step(run_id, "reviewer", reviewer_input)
                    reviewer_resp = await run_reviewer(reviewer_input, context_id=reviewer_context_id)
                    reviewer_output = str(reviewer_resp.get("response", ""))
                    reviewer_context_id = str(reviewer_resp.get("context_id", "")) or reviewer_context_id
                    verdict = parse_verdict(reviewer_output)
                    last_done = extract_last_done_thing(reviewer_output, verdict)

                    if verdict == "APPROVE":
                        self._finish_step(
                            current_step_id,
                            status="passed",
                            output_payload=reviewer_output,
                            agent_context_id=reviewer_context_id,
                        )
                        self._mark_current_task_step(run_id, "done")
                        self._set_run_status(run_id, "success", last_done_thing=last_done)
                        self._event(run_id, "info", "Run approved", {"verdict": verdict, "iterations": debug_iterations})
                        # Clean workspace on APPROVE
                        cleaned = _clean_worker_workspace(run_id)
                        if cleaned:
                            self._event(run_id, "info", "Workspace cleaned after APPROVE", {"path": workspace_str})

                        if self._auto_loop_enabled:
                            await self._start_next_run(
                                from_run_id=run_id,
                                profile_id=run["profile_id"],
                                goal=run["goal"],
                                global_context=run.get("global_context", "") or "",
                                last_done_thing=last_done,
                            )
                        else:
                            self._event(run_id, "info", "Auto-loop paused; next run not started")
                        return

                    if verdict == "BLOCKED_INFRA":
                        self._finish_step(
                            current_step_id,
                            status="blocked",
                            output_payload=reviewer_output,
                            agent_context_id=reviewer_context_id,
                        )
                        self._mark_current_task_step(run_id, "blocked")
                        self._set_run_status(run_id, "blocked", last_done_thing=last_done)
                        self._event(run_id, "warn", "Run infra blocked", {"verdict": verdict})
                        return

                    # REQUEST_CHANGES - continue loop
                    self._finish_step(
                        current_step_id,
                        status="failed",
                        output_payload=reviewer_output,
                        agent_context_id=reviewer_context_id,
                    )
                    self._event(run_id, "info", "Reviewer requested changes - continuing debug loop", {"iteration": debug_iterations})
                    # Continue loop for REQUEST_CHANGES

                # Max iterations reached without APPROVE
                self._event(run_id, "warn", f"Max debug iterations ({MAX_DEBUG_ITERATIONS}) reached without APPROVE")
                self._mark_current_task_step(run_id, "in_progress")
                self._set_run_status(run_id, "failed", last_done_thing=last_done)
                return
            else:
                worker_output = self._latest_passed_output(run_id, "worker")



        except asyncio.CancelledError:
            is_pause = run_id in self._pause_requests
            is_stop = run_id in self._stop_requests

            if current_step_id is not None:
                if is_pause:
                    self._finish_step(current_step_id, status="paused", error="Paused by user")
                elif is_stop:
                    self._finish_step(current_step_id, status="cancelled", error="Cancelled by user")
                else:
                    self._finish_step(current_step_id, status="failed", error="Cancelled unexpectedly")

            if is_pause:
                self._set_run_status(run_id, "paused")
                self._event(run_id, "info", "Pipeline paused by user")
            elif is_stop:
                self._mark_current_task_step(run_id, "cancelled")
                self._set_run_status(run_id, "cancelled")
                self._event(run_id, "warn", "Pipeline cancelled by user")
            else:
                self._set_run_status(run_id, "failed")
                self._event(run_id, "warn", "Pipeline cancelled unexpectedly")
            return
        except Exception as e:
            if current_step_id is not None:
                self._finish_step(current_step_id, status="failed", error=str(e))
                self._event(
                    run_id,
                    "error",
                    "Step execution failed",
                    {"step": current_step_name, "error": str(e)},
                )
            self._set_run_status(run_id, "failed")
            self._event(run_id, "error", "Pipeline execution error", {"error": str(e)})


runner = TriadRunner()


def latest_step_statuses(run_id: int) -> dict[str, dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT rs.*
        FROM run_steps rs
        INNER JOIN (
            SELECT step_name, MAX(attempt) AS max_attempt
            FROM run_steps
            WHERE run_id=?
            GROUP BY step_name
        ) latest
        ON rs.step_name = latest.step_name
        AND rs.attempt = latest.max_attempt
        WHERE rs.run_id=?
        ORDER BY CASE rs.step_name
            WHEN 'planner' THEN 1
            WHEN 'worker' THEN 2
            WHEN 'reviewer' THEN 3
            ELSE 99 END
        """,
        (run_id, run_id),
    )

    mapped: dict[str, dict[str, Any]] = {
        "planner": {"step_name": "planner", "status": "pending"},
        "worker": {"step_name": "worker", "status": "pending"},
        "reviewer": {"step_name": "reviewer", "status": "pending"},
    }
    for r in rows:
        mapped[r["step_name"]] = r
    return mapped

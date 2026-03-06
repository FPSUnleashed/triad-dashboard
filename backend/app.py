from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
import os

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import ALLOWED_ORIGINS, MAX_CONTEXT_SIZE, MAX_GOAL_SIZE, MAX_PROMPT_SIZE
from .db import execute, fetch_all, fetch_one, init_db, insert_and_get_id, json_dumps, utc_now
from .runner import latest_step_statuses, runner

import psutil

# Load secrets from .a0proj/secrets.env
secrets_file = Path(__file__).parent.parent / ".a0proj" / "secrets.env"
if secrets_file.exists():
    with open(secrets_file) as f:
        for line in f:
            line = line.strip()
            if line and "=" in line and not line.startswith("#"):
                key, val = line.split("=", 1)
                os.environ[key] = val.strip('"').strip("'")

app = FastAPI(title="Triad Dashboard API", version="0.2.0")
r = APIRouter(prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def parse_dt(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return None


def calc_duration_seconds(start: str | None, end: str | None) -> float | None:
    start_dt = parse_dt(start)
    end_dt = parse_dt(end)
    if start_dt and end_dt:
        return (end_dt - start_dt).total_seconds()
    return None


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours = minutes // 60
    minutes = minutes % 60
    return f"{hours}h {minutes}m"


def add_timing_to_step(step: dict) -> dict:
    step["duration_seconds"] = calc_duration_seconds(step.get("started_at"), step.get("ended_at"))
    step["duration_formatted"] = format_duration(step["duration_seconds"])
    return step


class ProfilePayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    planner_prompt: str = Field(min_length=1, max_length=MAX_PROMPT_SIZE)
    worker_inject_prompt: str = Field(min_length=1, max_length=MAX_PROMPT_SIZE)
    reviewer_inject_prompt: str = Field(min_length=1, max_length=MAX_PROMPT_SIZE)


class RunCreatePayload(BaseModel):
    goal: str = Field(min_length=1, max_length=MAX_GOAL_SIZE)
    profile_id: int
    global_context: str = Field(default="", max_length=MAX_CONTEXT_SIZE)
    last_done_thing: str = Field(default="", max_length=MAX_CONTEXT_SIZE)


class RetryPayload(BaseModel):
    step: Literal["planner", "worker", "reviewer"]


@app.on_event("startup")
def startup() -> None:
    init_db()

    existing = fetch_one("SELECT id FROM prompt_profiles WHERE name=?", ("default",))
    if not existing:
        now = utc_now()
        insert_and_get_id(
            """
            INSERT INTO prompt_profiles(name, planner_prompt, worker_inject_prompt, reviewer_inject_prompt, created_at, updated_at)
            VALUES(?,?,?,?,?,?)
            """,
            (
                "default",
                "You are the Planner. Create the next highest-value task based on project context, GitHub state, and last done thing.",
                "You are the Worker. Execute the task exactly and prepare a detailed PR-style delivery packet.",
                "You are the Reviewer. Review the Worker delivery and return APPROVE, REQUEST_CHANGES, or BLOCKED_INFRA with evidence.",
                now,
                now,
            ),
        )


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@r.get("/loop/state")
def loop_state() -> dict:
    return {"auto_loop_enabled": runner.auto_loop_enabled}


@r.post("/loop/pause")
def pause_loop() -> dict:
    enabled = runner.set_auto_loop_enabled(False)
    return {"ok": True, "auto_loop_enabled": enabled}


@r.post("/loop/resume")
def resume_loop() -> dict:
    enabled = runner.set_auto_loop_enabled(True)
    return {"ok": True, "auto_loop_enabled": enabled}


@r.get("/profiles")
def list_profiles() -> list[dict]:
    return fetch_all("SELECT * FROM prompt_profiles ORDER BY updated_at DESC, id DESC")


@r.post("/profiles")
def upsert_profile(payload: ProfilePayload) -> dict:
    now = utc_now()
    existing = fetch_one("SELECT id FROM prompt_profiles WHERE name=?", (payload.name,))
    if existing:
        execute(
            """
            UPDATE prompt_profiles
            SET planner_prompt=?, worker_inject_prompt=?, reviewer_inject_prompt=?, updated_at=?
            WHERE id=?
            """,
            (
                payload.planner_prompt,
                payload.worker_inject_prompt,
                payload.reviewer_inject_prompt,
                now,
                existing["id"],
            ),
        )
        profile = fetch_one("SELECT * FROM prompt_profiles WHERE id=?", (existing["id"],))
        return profile or {}

    new_id = insert_and_get_id(
        """
        INSERT INTO prompt_profiles(name, planner_prompt, worker_inject_prompt, reviewer_inject_prompt, created_at, updated_at)
        VALUES(?,?,?,?,?,?)
        """,
        (
            payload.name,
            payload.planner_prompt,
            payload.worker_inject_prompt,
            payload.reviewer_inject_prompt,
            now,
            now,
        ),
    )
    profile = fetch_one("SELECT * FROM prompt_profiles WHERE id=?", (new_id,))
    return profile or {}


@r.get("/stats")
def get_stats() -> dict:
    runs_row = fetch_one("SELECT COUNT(*) as count FROM runs", ())
    total_runs = runs_row["count"] if runs_row else 0

    status_rows = fetch_all("SELECT status, COUNT(*) as count FROM runs GROUP BY status", ())
    status_counts = {r["status"]: r["count"] for r in status_rows}

    time_rows = fetch_all(
        """
        SELECT
            step_name,
            SUM(CAST((julianday(ended_at) - julianday(started_at)) * 86400 AS REAL)) as total_seconds,
            COUNT(*) as step_count
        FROM run_steps
        WHERE started_at IS NOT NULL AND ended_at IS NOT NULL
        GROUP BY step_name
        """,
        (),
    )

    step_stats = {}
    total_all_steps = 0.0
    for r0 in time_rows:
        secs = r0["total_seconds"] or 0
        total_all_steps += secs
        step_stats[r0["step_name"]] = {
            "total_seconds": secs,
            "total_formatted": format_duration(secs),
            "step_count": r0["step_count"],
            "avg_seconds": secs / r0["step_count"] if r0["step_count"] else 0,
            "avg_formatted": format_duration(secs / r0["step_count"]) if r0["step_count"] else "-",
        }

    for step in ["planner", "worker", "reviewer"]:
        if step not in step_stats:
            step_stats[step] = {
                "total_seconds": 0,
                "total_formatted": "-",
                "step_count": 0,
                "avg_seconds": 0,
                "avg_formatted": "-",
            }

    return {
        "total_runs": total_runs,
        "status_counts": status_counts,
        "step_stats": step_stats,
        "total_all_steps_seconds": total_all_steps,
        "total_all_steps_formatted": format_duration(total_all_steps),
    }


@r.get("/runs")
def list_runs(limit: int = 20) -> list[dict]:
    lim = max(1, min(limit, 200))
    runs = fetch_all(
        """
        SELECT r.*, p.name AS profile_name
        FROM runs r
        LEFT JOIN prompt_profiles p ON p.id = r.profile_id
        ORDER BY r.id DESC
        LIMIT ?
        """,
        (lim,),
    )

    for run in runs:
        steps = fetch_all(
            "SELECT started_at, ended_at FROM run_steps WHERE run_id=? AND started_at IS NOT NULL AND ended_at IS NOT NULL",
            (run["id"],),
        )
        total_secs = sum(calc_duration_seconds(s["started_at"], s["ended_at"]) or 0 for s in steps)
        run["duration_seconds"] = total_secs
        run["duration_formatted"] = format_duration(total_secs)

    return runs


@r.post("/runs")
async def create_run(payload: RunCreatePayload) -> dict:
    profile = fetch_one("SELECT id FROM prompt_profiles WHERE id=?", (payload.profile_id,))
    if not profile:
        raise HTTPException(status_code=400, detail="profile_id not found")

    now = utc_now()
    run_id = insert_and_get_id(
        """
        INSERT INTO runs(goal, global_context, last_done_thing, status, profile_id, created_at, updated_at)
        VALUES(?,?,?,?,?,?,?)
        """,
        (
            payload.goal,
            payload.global_context,
            payload.last_done_thing,
            "running",
            payload.profile_id,
            now,
            now,
        ),
    )

    execute(
        "INSERT INTO run_events(run_id, level, message, meta, created_at) VALUES(?,?,?,?,?)",
        (run_id, "info", "Run created", json_dumps({"goal": payload.goal}), utc_now()),
    )

    try:
        await runner.start(run_id, "planner")
    except Exception as e:
        execute("UPDATE runs SET status=?, updated_at=? WHERE id=?", ("failed", utc_now(), run_id))
        execute(
            "INSERT INTO run_events(run_id, level, message, meta, created_at) VALUES(?,?,?,?,?)",
            (run_id, "error", "Failed to start run", json_dumps({"error": str(e)}), utc_now()),
        )
        raise HTTPException(status_code=500, detail=str(e))

    run = fetch_one("SELECT * FROM runs WHERE id=?", (run_id,))
    steps = latest_step_statuses(run_id)
    for step in steps.values():
        add_timing_to_step(step)
    return {"run": run, "step_status": steps}


@r.get("/runs/{run_id}")
def get_run(run_id: int) -> dict:
    run = fetch_one(
        """
        SELECT r.*, p.name AS profile_name
        FROM runs r
        LEFT JOIN prompt_profiles p ON p.id = r.profile_id
        WHERE r.id=?
        """,
        (run_id,),
    )
    if not run:
        raise HTTPException(status_code=404, detail="run not found")

    steps_time = fetch_all(
        "SELECT started_at, ended_at FROM run_steps WHERE run_id=? AND started_at IS NOT NULL AND ended_at IS NOT NULL",
        (run_id,),
    )
    total_secs = sum(calc_duration_seconds(s["started_at"], s["ended_at"]) or 0 for s in steps_time)
    run["duration_seconds"] = total_secs
    run["duration_formatted"] = format_duration(total_secs)

    if run["status"] == "running":
        first_started = fetch_one(
            "SELECT started_at FROM run_steps WHERE run_id=? AND started_at IS NOT NULL ORDER BY started_at ASC LIMIT 1",
            (run_id,),
        )
        if first_started and first_started.get("started_at"):
            start = datetime.fromisoformat(str(first_started["started_at"]).replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            elapsed_secs = (now - start).total_seconds()
            run["elapsed_seconds"] = elapsed_secs
            run["elapsed_formatted"] = format_duration(elapsed_secs)

    steps_raw = fetch_all(
        "SELECT step_name, status, started_at, ended_at FROM run_steps WHERE run_id=?",
        (run_id,),
    )
    steps = [add_timing_to_step(s) for s in steps_raw]
    step_status: dict = {}
    for step in steps:
        step_status[step["step_name"]] = {
            "step_name": step["step_name"],
            "status": step["status"],
            "duration_seconds": step["duration_seconds"],
            "duration_formatted": step["duration_formatted"],
        }

    for step_name in ["planner", "worker", "reviewer"]:
        if step_name not in step_status:
            step_status[step_name] = {"step_name": step_name, "status": "pending"}

    return {
        "run": run,
        "is_running": run["status"] == "running",
        "step_status": step_status,
    }


@r.get("/runs/{run_id}/steps")
def get_run_steps(run_id: int) -> list[dict]:
    run = fetch_one("SELECT id FROM runs WHERE id=?", (run_id,))
    if not run:
        raise HTTPException(status_code=404, detail="run not found")

    steps = fetch_all(
        """
        SELECT *
        FROM run_steps
        WHERE run_id=?
        ORDER BY
            CASE step_name
                WHEN 'planner' THEN 1
                WHEN 'worker' THEN 2
                WHEN 'reviewer' THEN 3
                ELSE 99
            END,
            attempt ASC,
            id ASC
        """,
        (run_id,),
    )

    return [add_timing_to_step(s) for s in steps]


@r.get("/runs/{run_id}/events")
def get_run_events(run_id: int) -> list[dict]:
    run = fetch_one("SELECT id FROM runs WHERE id=?", (run_id,))
    if not run:
        raise HTTPException(status_code=404, detail="run not found")

    return fetch_all("SELECT * FROM run_events WHERE run_id=? ORDER BY id ASC", (run_id,))


@r.post("/runs/{run_id}/stop")
def stop_run(run_id: int) -> dict:
    run = fetch_one("SELECT * FROM runs WHERE id=?", (run_id,))
    if not run:
        raise HTTPException(status_code=404, detail="run not found")

    result = runner.stop(run_id, reason="Cancelled by user from dashboard")
    return {"ok": True, "run_id": run_id, **result}


@r.post("/runs/{run_id}/pause")
def pause_run(run_id: int) -> dict:
    run = fetch_one("SELECT * FROM runs WHERE id=?", (run_id,))
    if not run:
        raise HTTPException(status_code=404, detail="run not found")

    if run.get("status") != "running":
        raise HTTPException(status_code=409, detail="only running runs can be paused")

    result = runner.pause(run_id, reason="Paused by user from dashboard")
    return {"ok": True, "run_id": run_id, **result}


@r.post("/runs/{run_id}/resume")
async def resume_run(run_id: int) -> dict:
    run = fetch_one("SELECT * FROM runs WHERE id=?", (run_id,))
    if not run:
        raise HTTPException(status_code=404, detail="run not found")

    try:
        result = await runner.resume(run_id)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"ok": True, "run_id": run_id, **result}


@r.post("/runs/{run_id}/retry")
async def retry_run(run_id: int, payload: RetryPayload) -> dict:
    run = fetch_one("SELECT * FROM runs WHERE id=?", (run_id,))
    if not run:
        raise HTTPException(status_code=404, detail="run not found")

    if runner.is_running(run_id):
        raise HTTPException(status_code=409, detail="run is currently running")

    execute("UPDATE runs SET status=?, updated_at=? WHERE id=?", ("running", utc_now(), run_id))
    execute(
        "INSERT INTO run_events(run_id, level, message, meta, created_at) VALUES(?,?,?,?,?)",
        (run_id, "info", "Retry requested", json_dumps({"step": payload.step}), utc_now()),
    )

    try:
        await runner.start(run_id, payload.step)
    except Exception as e:
        execute("UPDATE runs SET status=?, updated_at=? WHERE id=?", ("failed", utc_now(), run_id))
        execute(
            "INSERT INTO run_events(run_id, level, message, meta, created_at) VALUES(?,?,?,?,?)",
            (run_id, "error", "Retry failed to start", json_dumps({"error": str(e)}), utc_now()),
        )
        raise HTTPException(status_code=500, detail=str(e))

    return {"ok": True, "run_id": run_id, "restarted_from": payload.step}


@r.post("/runs/{run_id}/rerun-reviewer")
async def rerun_reviewer(run_id: int) -> dict:
    return await retry_run(run_id, RetryPayload(step="reviewer"))



@r.get("/system/metrics")
def system_metrics() -> dict:
    cpu_percent = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()

    # Detect running QEMU VM
    vm_running = False
    vm_info = {}
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if "qemu" in (proc.info["name"] or "").lower():
                vm_running = True
                cmdline = proc.info.get("cmdline") or []
                cmdline_str = " ".join(cmdline)
                # Extract RAM allocation from -m flag
                vm_ram = "-"
                for i, arg in enumerate(cmdline):
                    if arg == "-m" and i + 1 < len(cmdline):
                        vm_ram = cmdline[i + 1]
                        break
                # Check if KVM is in use
                kvm = "kvm" in cmdline_str.lower()
                vm_info = {"pid": proc.info["pid"], "ram_alloc": vm_ram, "kvm": kvm}
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return {
        "cpu_percent": round(cpu_percent, 1),
        "ram_used_gb": round(mem.used / (1024 ** 3), 1),
        "ram_total_gb": round(mem.total / (1024 ** 3), 1),
        "ram_percent": round(mem.percent, 1),
        "vm_running": vm_running,
        "vm_info": vm_info,
    }

app.include_router(r)

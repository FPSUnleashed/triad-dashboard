#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = PROJECT_ROOT / 'vms' / 'runs'
EVIDENCE_DIR = PROJECT_ROOT / 'vms' / 'evidence'


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def safe_read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding='utf-8').strip())
    except Exception:
        return None


def latest_run_dir() -> Path:
    candidates = [p for p in RUNS_DIR.iterdir() if p.is_dir() and (p / 'run.json').exists()]
    if not candidates:
        raise SystemExit(f'No VM runs found in {RUNS_DIR}')
    candidates.sort(key=lambda p: (p / 'run.json').stat().st_mtime, reverse=True)
    return candidates[0]


def resolve_run_dir(args: argparse.Namespace) -> Path:
    if args.run_dir:
        rdir = Path(args.run_dir).resolve()
    elif args.run_name:
        rdir = (RUNS_DIR / args.run_name).resolve()
    else:
        rdir = latest_run_dir().resolve()
    if not (rdir / 'run.json').exists():
        raise SystemExit(f'Missing run manifest: {rdir / "run.json"}')
    return rdir


def tail_file(path: Path, lines: int) -> list[str]:
    if not path.exists():
        return []
    try:
        data = path.read_text(encoding='utf-8', errors='replace').splitlines()
        return data[-lines:]
    except Exception as exc:
        return [f'<failed to read {path}: {exc}>']


def capture_screen(run_dir: Path, capture_dir: Path) -> dict[str, Any]:
    monitor = run_dir / 'qemu-monitor.sock'
    if not monitor.exists():
        return {
            'requested': True,
            'success': False,
            'reason': f'monitor socket not found: {monitor}',
            'ppm_path': None,
            'png_path': None,
        }

    capture_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    ppm_path = capture_dir / f'vm_screen_{run_dir.name}_{stamp}.ppm'
    png_path = capture_dir / f'vm_screen_{run_dir.name}_{stamp}.png'

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect(str(monitor))
        time.sleep(0.2)
        try:
            sock.recv(4096)
        except Exception:
            pass
        sock.sendall(f'screendump {ppm_path}\n'.encode())
        time.sleep(1.0)
        try:
            sock.recv(4096)
        except Exception:
            pass
        sock.close()
    except Exception as exc:
        return {
            'requested': True,
            'success': False,
            'reason': f'failed to capture from monitor socket: {exc}',
            'ppm_path': str(ppm_path),
            'png_path': None,
        }

    if not ppm_path.exists():
        return {
            'requested': True,
            'success': False,
            'reason': 'monitor command returned but no PPM file was created',
            'ppm_path': str(ppm_path),
            'png_path': None,
        }

    png_created = False
    convert_bin = shutil.which('convert')
    if convert_bin:
        try:
            subprocess.run([convert_bin, str(ppm_path), str(png_path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            png_created = png_path.exists()
        except Exception:
            png_created = False

    return {
        'requested': True,
        'success': True,
        'reason': 'screen captured from qemu monitor',
        'ppm_path': str(ppm_path),
        'png_path': str(png_path) if png_created else None,
    }


def effective_state(manifest_status: str | None, qemu_alive_now: bool, overlay_exists: bool, ovmf_exists: bool, monitor_exists: bool) -> str:
    if not overlay_exists or not ovmf_exists:
        return 'invalid_missing_run_artifacts'
    if qemu_alive_now:
        if monitor_exists:
            return 'running_ready_for_observation'
        return 'running_without_monitor_socket'
    if manifest_status == 'running':
        return 'stale_manifest_process_dead'
    return 'stopped'


def next_action_hint(state: str, has_capture: bool) -> str:
    if state == 'running_ready_for_observation' and has_capture:
        return 'Run zai-vision on the captured screen, classify the visible Windows/app state, then take one bounded action only if justified.'
    if state == 'running_ready_for_observation':
        return 'Capture a screen from the monitor socket, then analyze it with zai-vision before acting.'
    if state == 'running_without_monitor_socket':
        return 'Inspect qemu logs or stop and recreate the run; reliable screen observation is not currently available.'
    if state == 'stale_manifest_process_dead':
        return 'Treat this run as stopped; either restart it or create a fresh run if contamination risk exists.'
    if state == 'invalid_missing_run_artifacts':
        return 'Destroy this run and create a new fresh run from the baseline before continuing.'
    return 'Start the run if VM interaction is needed, or inspect existing evidence/logs if only postmortem analysis is required.'


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = resolve_run_dir(args)
    manifest = safe_read_json(run_dir / 'run.json')

    qemu_pid = read_pid(run_dir / 'qemu.pid') or manifest.get('pid')
    websockify_pid = read_pid(run_dir / 'websockify.pid') or manifest.get('websockify_pid')
    qemu_alive_now = pid_alive(qemu_pid)
    websockify_alive_now = pid_alive(websockify_pid)

    overlay_path = Path(manifest.get('overlay_disk', run_dir / 'overlay.qcow2'))
    ovmf_path = Path(manifest.get('ovmf_vars', run_dir / 'OVMF_VARS.fd'))
    monitor_path = run_dir / 'qemu-monitor.sock'
    serial_log = run_dir / 'qemu_serial.log'
    qemu_debug_log = run_dir / 'qemu_debug.log'
    websockify_log = run_dir / 'websockify.log'

    state = effective_state(
        manifest.get('status'),
        qemu_alive_now,
        overlay_path.exists(),
        ovmf_path.exists(),
        monitor_path.exists(),
    )

    capture = {
        'requested': False,
        'success': False,
        'reason': 'screen capture not requested',
        'ppm_path': None,
        'png_path': None,
    }
    if args.capture_screen:
        out_dir = Path(args.capture_dir).resolve() if args.capture_dir else (EVIDENCE_DIR / 'situation_reports')
        capture = capture_screen(run_dir, out_dir)

    screenshot_path = capture.get('png_path') or capture.get('ppm_path')

    host_observation = []
    host_observation.append(f'run manifest status={manifest.get("status", "unknown")} effective_state={state}')
    host_observation.append(f'qemu_pid={qemu_pid} alive={qemu_alive_now}')
    host_observation.append(f'websockify_pid={websockify_pid} alive={websockify_alive_now}')
    host_observation.append(f'monitor_socket_exists={monitor_path.exists()} overlay_exists={overlay_path.exists()} ovmf_exists={ovmf_path.exists()}')
    if screenshot_path:
        host_observation.append(f'screenshot_available={screenshot_path}')

    suggested_vision_command = None
    if screenshot_path:
        question = args.vision_question or 'Read all visible text exactly, classify the current Windows/app state, identify any errors or blockers, and say what the next safe bounded action should be.'
        suggested_vision_command = f'python /a0/usr/skills/zai-vision/analyze.py {screenshot_path} {json.dumps(question)}'

    report = {
        'generated_at': utc_now(),
        'goal': args.goal,
        'artifact_under_test': args.artifact,
        'expected_postcondition': args.expected_postcondition,
        'run_name': manifest.get('run_name', run_dir.name),
        'run_dir': str(run_dir),
        'baseline': manifest.get('baseline'),
        'manifest_status': manifest.get('status'),
        'effective_state': state,
        'host_state_confidence': 'high',
        'screen_state': 'unknown' if not screenshot_path else 'requires_vision_classification',
        'screen_state_confidence': 'low' if not screenshot_path else 'medium',
        'created_at': manifest.get('created_at'),
        'started_at': manifest.get('started_at'),
        'stopped_at': manifest.get('stopped_at'),
        'qemu_pid': qemu_pid,
        'qemu_alive': qemu_alive_now,
        'websockify_pid': websockify_pid,
        'websockify_alive': websockify_alive_now,
        'vnc_port': manifest.get('vnc_port'),
        'novnc_port': manifest.get('novnc_port'),
        'novnc_url': manifest.get('novnc_url'),
        'monitor_socket': str(monitor_path),
        'overlay_disk': str(overlay_path),
        'ovmf_vars': str(ovmf_path),
        'capture': capture,
        'host_observation_summary': host_observation,
        'suggested_vision_command': suggested_vision_command,
        'next_action_hint': next_action_hint(state, bool(screenshot_path)),
        'evidence_paths': {
            'run_manifest': str(run_dir / 'run.json'),
            'serial_log': str(serial_log) if serial_log.exists() else None,
            'qemu_debug_log': str(qemu_debug_log) if qemu_debug_log.exists() else None,
            'websockify_log': str(websockify_log) if websockify_log.exists() else None,
            'latest_screen_ppm': capture.get('ppm_path'),
            'latest_screen_png': capture.get('png_path'),
        },
        'log_tails': {
            'qemu_serial_log_tail': tail_file(serial_log, args.tail_lines),
            'qemu_debug_log_tail': tail_file(qemu_debug_log, args.tail_lines),
            'websockify_log_tail': tail_file(websockify_log, args.tail_lines),
        },
    }

    report['situation_report_text'] = '\n'.join([
        'SITUATION_REPORT',
        f'- Goal: {args.goal or "(not provided)"}',
        f'- Run dir: {report["run_dir"]}',
        f'- Artifact under test: {args.artifact or "(not provided)"}',
        f'- Effective host state: {state}',
        f'- Screen state: {report["screen_state"]}',
        f'- Screenshot: {screenshot_path or "(none)"}',
        f'- Confidence: host={report["host_state_confidence"]}, screen={report["screen_state_confidence"]}',
        f'- Next action hint: {report["next_action_hint"]}',
        f'- Expected postcondition: {args.expected_postcondition or "(not provided)"}',
    ])
    return report


def print_text(report: dict[str, Any]) -> None:
    print(report['situation_report_text'])
    print('\nHOST_OBSERVATION_SUMMARY')
    for line in report['host_observation_summary']:
        print(f'- {line}')
    print('\nEVIDENCE_PATHS')
    for key, value in report['evidence_paths'].items():
        print(f'- {key}: {value}')
    if report.get('suggested_vision_command'):
        print('\nSUGGESTED_VISION_COMMAND')
        print(report['suggested_vision_command'])
    print('\nLOG_TAILS')
    for key, lines in report['log_tails'].items():
        print(f'[{key}]')
        if lines:
            for line in lines:
                print(line)
        else:
            print('<no data>')


def main() -> int:
    p = argparse.ArgumentParser(description='Generate an agent-friendly VM situation report for a Triad VM run')
    p.add_argument('--run-name', help='VM run name inside vms/runs/')
    p.add_argument('--run-dir', help='Absolute or relative path to the VM run directory')
    p.add_argument('--goal', help='Bounded scenario goal to include in the report')
    p.add_argument('--artifact', help='Artifact under test to include in the report')
    p.add_argument('--expected-postcondition', help='Expected postcondition after the next action')
    p.add_argument('--capture-screen', action='store_true', help='Capture a screenshot from the QEMU monitor socket')
    p.add_argument('--capture-dir', help='Directory for captured screenshots (default: vms/evidence/situation_reports)')
    p.add_argument('--vision-question', help='Question to embed into the suggested zai-vision command')
    p.add_argument('--tail-lines', type=int, default=12, help='Number of log lines to include from each log')
    p.add_argument('--format', choices=['text', 'json'], default='text', help='Output format')
    args = p.parse_args()

    report = build_report(args)
    if args.format == 'json':
        print(json.dumps(report, indent=2))
    else:
        print_text(report)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

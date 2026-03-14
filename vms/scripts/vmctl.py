#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
VMS = ROOT / 'vms'
CFG_PATH = VMS / 'vm_runtime_config.json'
BASELINES = VMS / 'baselines'
RUNS = VMS / 'runs'


def now_stamp() -> str:
    return dt.datetime.utcnow().strftime('%Y%m%d_%H%M%S')


def now_iso() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'


def load_cfg() -> dict:
    if not CFG_PATH.exists():
        raise SystemExit(f'Missing config: {CFG_PATH}')
    return json.loads(CFG_PATH.read_text(encoding='utf-8'))


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def run(cmd: list[str], capture: bool = False) -> str:
    print('+', ' '.join(cmd))
    if capture:
        out = subprocess.run(cmd, check=True, text=True, capture_output=True)
        return out.stdout
    subprocess.run(cmd, check=True)
    return ''


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding='utf-8').strip())
    except Exception:
        return None


def port_in_use(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        return s.connect_ex(('127.0.0.1', port)) == 0
    finally:
        s.close()


def novnc_port(cfg: dict) -> int:
    url = cfg.get('novnc_url', 'http://localhost:6080')
    parsed = urlparse(url)
    return parsed.port or 6080


def vnc_port(cfg: dict) -> int:
    return int(cfg.get('vnc_port', 5900))


def vnc_display_num(cfg: dict) -> int:
    return vnc_port(cfg) - 5900


def ovmf_code_path() -> Path:
    candidates = [
        Path('/usr/share/OVMF/OVMF_CODE_4M.fd'),
        Path('/usr/share/OVMF/OVMF_CODE.fd'),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise SystemExit('Could not locate OVMF_CODE firmware file under /usr/share/OVMF')


def resolve_source_disk(cfg: dict, override: str | None) -> Path:
    candidates: list[Path] = []
    if override:
        candidates.append(Path(override))
    disk_image = cfg.get('disk_image')
    if disk_image:
        candidates.append(Path(disk_image))
    candidates.extend([
        VMS / 'media' / 'WinDev2407Eval.vhdx',
        VMS / 'WinDev2407Eval.vhdx',
    ])
    checked = []
    for candidate in candidates:
        checked.append(str(candidate))
        if candidate.exists():
            return candidate.resolve()
    raise SystemExit('No VM disk image found. Checked:\n- ' + '\n- '.join(checked))


def qemu_running_for_path(path: Path) -> bool:
    try:
        out = subprocess.run(['pgrep', '-fa', 'qemu-system-x86_64'], check=False, text=True, capture_output=True).stdout
    except Exception:
        return False
    return str(path) in out


def baseline_dir(name: str) -> Path:
    return BASELINES / name


def baseline_disk(name: str) -> Path:
    return baseline_dir(name) / 'base_disk.qcow2'


def baseline_vars(name: str) -> Path:
    return baseline_dir(name) / 'OVMF_VARS_base.fd'


def baseline_manifest(name: str) -> Path:
    return baseline_dir(name) / 'manifest.json'


def ensure_baseline(name: str) -> None:
    bdir = baseline_dir(name)
    if not bdir.exists() or not baseline_disk(name).exists() or not baseline_vars(name).exists():
        raise SystemExit(f'Baseline {name!r} is incomplete. Expected files under {bdir}')


def capture_baseline(args: argparse.Namespace, emit: bool = True) -> dict:
    cfg = load_cfg()
    src_disk = resolve_source_disk(cfg, args.source_disk)
    src_vars = Path(args.source_vars) if args.source_vars else (VMS / 'OVMF_VARS.fd')
    if not src_vars.exists():
        raise SystemExit(f'Missing OVMF vars source: {src_vars}')
    if qemu_running_for_path(src_disk):
        raise SystemExit(f'Refusing baseline capture while QEMU is running from source disk: {src_disk}')

    bdir = baseline_dir(args.baseline)
    bdir.mkdir(parents=True, exist_ok=True)
    bdisk = baseline_disk(args.baseline)
    bvars = baseline_vars(args.baseline)
    manifest_path = baseline_manifest(args.baseline)

    if (bdisk.exists() or bvars.exists() or manifest_path.exists()) and not args.force:
        raise SystemExit(f'Baseline {args.baseline!r} already exists. Use --force to replace it.')

    for path in [bdisk, bvars, manifest_path]:
        if path.exists():
            path.unlink()

    run(['qemu-img', 'convert', '-p', '-O', 'qcow2', str(src_disk), str(bdisk)])
    shutil.copy2(src_vars, bvars)
    qinfo = subprocess.run(['qemu-img', 'info', str(bdisk)], check=True, text=True, capture_output=True).stdout.strip()

    data = {
        'baseline': args.baseline,
        'created_at': now_iso(),
        'source_disk': str(src_disk),
        'source_ovmf_vars': str(src_vars),
        'baseline_disk': str(bdisk),
        'baseline_ovmf_vars': str(bvars),
        'qemu_img_info': qinfo,
    }
    write_json(manifest_path, data)
    if emit:
        print(json.dumps(data, indent=2))
    return data


def create_run(args: argparse.Namespace, emit: bool = True) -> dict:
    ensure_baseline(args.baseline)
    cfg = load_cfg()
    run_name = args.run_name or f'{args.baseline}_{now_stamp()}'
    rdir = (RUNS / run_name).resolve()
    if rdir.exists():
        raise SystemExit(f'Run directory already exists: {rdir}')
    rdir.mkdir(parents=True)

    overlay = rdir / 'overlay.qcow2'
    rvars = rdir / 'OVMF_VARS.fd'
    shutil.copy2(baseline_vars(args.baseline), rvars)
    run(['qemu-img', 'create', '-f', 'qcow2', '-F', 'qcow2', '-b', str(baseline_disk(args.baseline)), str(overlay)])

    data = {
        'run_name': run_name,
        'created_at': now_iso(),
        'status': 'created',
        'baseline': args.baseline,
        'run_dir': str(rdir),
        'overlay_disk': str(overlay),
        'ovmf_vars': str(rvars),
        'memory_mb': int(cfg.get('memory_mb', 4096)),
        'cpus': int(cfg.get('cpus', 2)),
        'acceleration': cfg.get('acceleration', 'kvm'),
        'vnc_port': vnc_port(cfg),
        'novnc_port': novnc_port(cfg),
    }
    write_json(rdir / 'run.json', data)
    if emit:
        print(json.dumps(data, indent=2))
    return data


def start_websockify(rdir: Path, nport: int, vport: int) -> int | None:
    pidfile = rdir / 'websockify.pid'
    existing = read_pid(pidfile)
    if pid_alive(existing):
        return existing
    web_dir = Path('/usr/share/novnc')
    if not web_dir.exists():
        return None
    if port_in_use(nport):
        return None
    log = open(rdir / 'websockify.log', 'ab')
    proc = subprocess.Popen(
        ['python3', '-m', 'websockify', '--web', str(web_dir), str(nport), f'localhost:{vport}'],
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    pidfile.write_text(str(proc.pid), encoding='utf-8')
    return proc.pid


def start_run(args: argparse.Namespace, emit: bool = True) -> dict:
    cfg = load_cfg()
    rdir = Path(args.run_dir).resolve()
    run_json = rdir / 'run.json'
    if not run_json.exists():
        raise SystemExit(f'Missing run manifest: {run_json}')
    data = read_json(run_json)

    overlay = Path(data['overlay_disk'])
    rvars = Path(data['ovmf_vars'])
    if not overlay.exists() or not rvars.exists():
        raise SystemExit('Run is missing overlay disk or OVMF vars copy')

    pidfile = rdir / 'qemu.pid'
    existing = read_pid(pidfile)
    if pid_alive(existing):
        data['status'] = 'running'
        data['pid'] = existing
        write_json(run_json, data)
        if emit:
            print(json.dumps(data, indent=2))
        return data

    vp = vnc_port(cfg)
    np = novnc_port(cfg)
    if port_in_use(vp):
        raise SystemExit(f'Configured VNC port {vp} is already in use. Stop the other VM first.')

    monitor = rdir / 'qemu-monitor.sock'
    serial_log = rdir / 'qemu_serial.log'
    debug_log = rdir / 'qemu_debug.log'
    name = cfg.get('name', 'triad_vm') + '-' + rdir.name

    cmd = [
        'qemu-system-x86_64',
        '-name', name,
        '-machine', f"q35,accel={cfg.get('acceleration', 'kvm')}",
        '-cpu', 'host',
        '-smp', str(int(cfg.get('cpus', 2))),
        '-m', str(int(cfg.get('memory_mb', 4096))),
        '-drive', f'if=pflash,format=raw,readonly=on,file={ovmf_code_path()}',
        '-drive', f'if=pflash,format=raw,file={rvars}',
        '-device', 'ich9-ahci,id=ahci',
        '-drive', f'file={overlay},if=none,id=windisk,format=qcow2,cache=writeback,aio=threads',
        '-device', 'ide-hd,drive=windisk,bus=ahci.0',
        '-boot', 'order=c',
        '-display', 'none',
        '-vnc', f'0.0.0.0:{vnc_display_num(cfg)}',
        '-netdev', 'user,id=n1',
        '-device', 'e1000,netdev=n1',
        '-monitor', f'unix:{monitor},server,nowait',
        '-no-shutdown',
        '-serial', f'file:{serial_log}',
        '-D', str(debug_log),
        '-daemonize',
        '-pidfile', str(pidfile),
    ]
    run(cmd)
    time.sleep(1)
    pid = read_pid(pidfile)
    if not pid_alive(pid):
        raise SystemExit(f'QEMU failed to start for run dir {rdir}')

    wpid = start_websockify(rdir, np, vp)
    data.update({
        'status': 'running',
        'started_at': now_iso(),
        'pid': pid,
        'vnc_port': vp,
        'novnc_port': np,
        'novnc_url': f'http://localhost:{np}/vnc.html?autoconnect=true&resize=remote',
        'websockify_pid': wpid,
    })
    write_json(run_json, data)
    if emit:
        print(json.dumps(data, indent=2))
    return data


def _wait_for_exit(pid: int | None, timeout: int) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if not pid_alive(pid):
            return True
        time.sleep(1)
    return not pid_alive(pid)


def stop_run(args: argparse.Namespace, emit: bool = True) -> dict:
    rdir = Path(args.run_dir).resolve()
    run_json = rdir / 'run.json'
    data = read_json(run_json) if run_json.exists() else {'run_dir': str(rdir)}
    pid = read_pid(rdir / 'qemu.pid')
    monitor = rdir / 'qemu-monitor.sock'

    if pid_alive(pid):
        if monitor.exists() and shutil.which('socat'):
            subprocess.run(
                ['socat', '-', f'UNIX-CONNECT:{monitor}'],
                input='system_powerdown\n',
                text=True,
                capture_output=True,
                check=False,
            )
            _wait_for_exit(pid, int(args.force_after))
        if pid_alive(pid):
            os.kill(pid, signal.SIGTERM)
            _wait_for_exit(pid, 5)
        if pid_alive(pid):
            os.kill(pid, signal.SIGKILL)

    wpid = read_pid(rdir / 'websockify.pid')
    if pid_alive(wpid):
        os.kill(wpid, signal.SIGTERM)

    data['status'] = 'stopped'
    data['stopped_at'] = now_iso()
    write_json(run_json, data)
    if emit:
        print(json.dumps(data, indent=2))
    return data


def destroy_run(args: argparse.Namespace, emit: bool = True) -> dict:
    rdir = Path(args.run_dir).resolve()
    stop_run(argparse.Namespace(run_dir=str(rdir), force_after=args.force_after), emit=False)

    removed = []
    for name in ['overlay.qcow2', 'OVMF_VARS.fd', 'qemu.pid', 'websockify.pid', 'qemu-monitor.sock']:
        path = rdir / name
        if path.exists():
            path.unlink()
            removed.append(str(path))

    run_json = rdir / 'run.json'
    if run_json.exists() and not args.purge_dir:
        data = read_json(run_json)
        data['status'] = 'destroyed'
        data['destroyed_at'] = now_iso()
        data['removed_paths'] = removed
        write_json(run_json, data)
    elif args.purge_dir and rdir.exists():
        shutil.rmtree(rdir)

    result = {
        'run_dir': str(rdir),
        'purged_dir': bool(args.purge_dir),
        'removed_paths': removed,
    }
    if emit:
        print(json.dumps(result, indent=2))
    return result


def status(args: argparse.Namespace) -> dict:
    cfg_exists = CFG_PATH.exists()
    baselines_list = []
    for bdir in sorted(BASELINES.iterdir() if BASELINES.exists() else []):
        if not bdir.is_dir():
            continue
        baselines_list.append({
            'name': bdir.name,
            'disk_exists': (bdir / 'base_disk.qcow2').exists(),
            'vars_exists': (bdir / 'OVMF_VARS_base.fd').exists(),
            'manifest': str(bdir / 'manifest.json') if (bdir / 'manifest.json').exists() else None,
        })

    runs_list = []
    for rdir in sorted(RUNS.iterdir() if RUNS.exists() else []):
        if not rdir.is_dir():
            continue
        pid = read_pid(rdir / 'qemu.pid')
        run_json = rdir / 'run.json'
        status_value = None
        if run_json.exists():
            try:
                status_value = read_json(run_json).get('status')
            except Exception:
                status_value = 'invalid-run-json'
        runs_list.append({
            'name': rdir.name,
            'run_dir': str(rdir),
            'running': pid_alive(pid),
            'pid': pid,
            'status': status_value,
        })

    data = {
        'config_exists': cfg_exists,
        'config_path': str(CFG_PATH),
        'baselines': baselines_list,
        'runs': runs_list,
    }
    print(json.dumps(data, indent=2))
    return data


def fresh_run(args: argparse.Namespace) -> dict:
    created = create_run(argparse.Namespace(baseline=args.baseline, run_name=args.run_name), emit=False)
    started = start_run(argparse.Namespace(run_dir=created['run_dir']), emit=False)
    print(json.dumps(started, indent=2))
    return started


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='Triad VM baseline/overlay manager')
    sub = p.add_subparsers(dest='cmd', required=True)

    s = sub.add_parser('capture-baseline')
    s.add_argument('--baseline', default='default')
    s.add_argument('--source-disk')
    s.add_argument('--source-vars')
    s.add_argument('--force', action='store_true')
    s.set_defaults(func=capture_baseline)

    s = sub.add_parser('create-run')
    s.add_argument('--baseline', default='default')
    s.add_argument('--run-name')
    s.set_defaults(func=create_run)

    s = sub.add_parser('start-run')
    s.add_argument('--run-dir', required=True)
    s.set_defaults(func=start_run)

    s = sub.add_parser('stop-run')
    s.add_argument('--run-dir', required=True)
    s.add_argument('--force-after', type=int, default=30)
    s.set_defaults(func=stop_run)

    s = sub.add_parser('destroy-run')
    s.add_argument('--run-dir', required=True)
    s.add_argument('--force-after', type=int, default=30)
    s.add_argument('--purge-dir', action='store_true')
    s.set_defaults(func=destroy_run)

    s = sub.add_parser('fresh-run')
    s.add_argument('--baseline', default='default')
    s.add_argument('--run-name')
    s.set_defaults(func=fresh_run)

    s = sub.add_parser('status')
    s.set_defaults(func=status)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

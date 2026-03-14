# VM Protocol

## Purpose
This VM exists to give the triad a repeatable Windows environment for real software validation.
The core model is:

- **Golden baseline** = clean Windows install that boots to desktop
- **Fresh run** = disposable overlay created from the golden baseline
- **Reviewer validation** = real user-like testing inside a fresh Windows run

## Files and directories

| Purpose | Path |
|---|---|
| Runtime config | `/a0/usr/projects/dashboard_triad_project/vms/vm_runtime_config.json` |
| VM protocol | `/a0/usr/projects/dashboard_triad_project/vms/VM_PROTOCOL.md` |
| Scripts | `/a0/usr/projects/dashboard_triad_project/vms/scripts/` |
| Golden baselines | `/a0/usr/projects/dashboard_triad_project/vms/baselines/` |
| Disposable runs | `/a0/usr/projects/dashboard_triad_project/vms/runs/` |
| Default mutable UEFI vars source | `/a0/usr/projects/dashboard_triad_project/vms/OVMF_VARS.fd` |

## Role contract

### Planner
- Planner never uses the VM directly.
- Planner must plan **one atomic step per cycle**.
- If reviewer feedback reports a defect, planner must prioritize the smallest repair step before new feature work.
- When work affects installer behavior, packaging, UI/UX, or user-facing flows, planner should expect reviewer evidence from a fresh VM scenario.

### Worker
- Worker may use the VM **like an engineer** for debugging, reproduction, or extra verification.
- Before any meaningful VM action, Worker should generate a **Situation Report** using `./vms/scripts/vm_situation_report.sh` when possible.
- Worker should still try hard not to ship bugs in the first place.
- Worker should prefer faster local verification first when appropriate.
- Worker must **never mutate the golden baseline directly**.
- If worker uses the VM, worker should start from a fresh run, preserve evidence, then stop the VM when done.
- Engineering-style VM checks do **not** replace reviewer user-style approval for installer/UI/user-facing flows.

### Reviewer
- Reviewer must use the VM **like a human user**.
- Before any meaningful VM action, Reviewer should generate a **Situation Report** using `./vms/scripts/vm_situation_report.sh` when possible.
- For installer changes, packaging changes, onboarding, UI/UX changes, or final approval of user-facing work, reviewer must test from a **fresh VM run**.
- Reviewer must use normal entrypoints and normal user interaction.
- Reviewer must inspect actual screen content, not just capture screenshots.
- Reviewer must test the changed feature and the most plausible adjacent regression surfaces touched by the change.
- Reviewer must create a **new fresh VM scenario** whenever prior actions contaminate results or the tested action is irreversible.

## Forbidden reviewer shortcuts
Reviewer must **not** use the following as substitutes for real user validation inside the VM:

- browser_agent
- direct route jumping
- API-only validation for user-facing flows
- file/database edits to simulate user results
- claiming success because a screenshot file exists

## Baseline model
The preferred checkpoint model is:

1. Capture the clean Windows machine into a **golden QCOW2 baseline**.
2. Copy the matching `OVMF_VARS` file into the baseline folder.
3. For each scenario, create a **QCOW2 overlay** backed by the baseline.
4. Boot the VM from the overlay.
5. When done, stop the VM and destroy the overlay.

This preserves a clean reusable Windows state and prevents stale contamination between scenarios.

## Standard commands

### Capture a golden baseline once
```bash
./vms/scripts/vm_capture_baseline.sh --baseline default --source-disk /path/to/windows_disk.vhdx
```

If `--source-disk` is omitted, the script will try the configured `disk_image` from `vm_runtime_config.json` and a couple of common fallback locations.

### Start a fresh disposable VM run
```bash
./vms/scripts/vm_fresh_run.sh --baseline default --run-name reviewer_scenario_01
```

This creates a new overlay and boots QEMU.

### Show VM state
```bash
./vms/scripts/vm_status.sh
```

### Generate an agent-friendly situation report
```bash
./vms/scripts/vm_situation_report.sh --run-name reviewer_scenario_01 --goal "Launch the installer" --artifact "C:\\Users\\User\\Desktop\\Setup.exe" --expected-postcondition "Installer wizard window becomes visible" --capture-screen
```

This produces a compact report with run state, evidence paths, log tails, optional screenshot capture, and a suggested `zai-vision` command for exact screen interpretation.

### Stop a VM run
```bash
./vms/scripts/vm_stop_run.sh --run-dir /a0/usr/projects/dashboard_triad_project/vms/runs/reviewer_scenario_01
```

### Destroy a disposable VM run
```bash
./vms/scripts/vm_destroy_run.sh --run-dir /a0/usr/projects/dashboard_triad_project/vms/runs/reviewer_scenario_01
```

By default, destroy removes the mutable overlay/vars/runtime files while keeping the run directory for evidence. Use `--purge-dir` if you want the whole directory removed.

## One fresh VM per scenario
Default rule:

- one **fresh VM run per review scenario**
- create additional fresh runs whenever:
  - prior actions contaminate the result
  - the action is destructive or irreversible
  - a second branch of behavior must be validated from a clean state

## Evidence expectations
If the VM is used for validation, capture and preserve:

- artifact path used for install/run
- screenshots
- OCR output where relevant
- logs
- run directory path

## Operational note
Only one VM run should normally be active at a time because the scripts use the configured VNC/noVNC ports from `vm_runtime_config.json`.

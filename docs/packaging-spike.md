# Packaging Spike Plan (Milestone 0)

## Goal
Create and validate a minimal Python sidecar packaging path for the Tauri host app, proving launch/readiness behavior and documenting platform caveats before broader rollout.

## Scope (Milestone 0)
- Package a hello-world Python sidecar as a standalone binary using **Nuitka**.
- Verify Tauri can launch the packaged binary via `externalBin`.
- Verify host-side READY detection by parsing sidecar stdout.
- Capture cross-platform issues in a standard log template.
- Define explicit fallback criteria and contingency steps for **PyInstaller**.

Out of scope:
- Full production sidecar feature set.
- Hardening, signing/notarization automation, and universal installer work.
- Multi-platform completion in Milestone 0 (only one platform is required for exit).

---

## 1) Minimal Python Sidecar “Hello World” Target (Nuitka)

### Deliverable
A small sidecar executable that:
1. starts successfully,
2. prints `READY` to stdout exactly once,
3. stays alive long enough for host verification (or serves a no-op loop),
4. exits cleanly on signal/termination.

### Suggested sidecar behavior
- On startup:
  - print `BOOT sidecar=<name> version=<x.y.z>`
  - print `READY`
- Runtime:
  - idle loop with periodic heartbeat optional (`HEARTBEAT` every N sec) for debugging.
- Shutdown:
  - print `SHUTDOWN reason=<signal|normal>`

### Suggested build command (example)
```bash
python -m nuitka sidecar/main.py \
  --onefile \
  --assume-yes-for-downloads \
  --output-dir=dist/nuitka
```

### Artifacts to capture
- Exact Nuitka command and version.
- Python version + platform/arch.
- Produced binary name/path and size.
- Cold-start latency (process launch to `READY`).

---

## 2) Validation Checklist: Tauri `externalBin` + READY Parsing

Use this checklist during spike execution.

### A. Tauri configuration
- [ ] `externalBin` path is configured for the sidecar binary target.
- [ ] Per-platform naming conventions are handled (`.exe` on Windows, none on macOS/Linux).
- [ ] Sidecar binary is included in app packaging output.

### B. Launch behavior
- [ ] Host invokes sidecar with expected args/env.
- [ ] Sidecar process starts without immediate crash.
- [ ] Host observes process PID and retains lifecycle handle.

### C. READY protocol parsing
- [ ] Host reads sidecar stdout stream reliably.
- [ ] Host detects `READY` token line exactly once.
- [ ] Host transitions internal state to “ready” only after READY token.
- [ ] READY timeout is enforced and emits actionable error logs.

### D. Failure-path checks
- [ ] Missing binary path returns clear startup error.
- [ ] Non-zero sidecar exit before READY is surfaced to UI/logs.
- [ ] Malformed stdout (no READY) triggers timeout path.
- [ ] Stderr output is captured and attached to diagnostics.

### E. Basic reliability checks
- [ ] App restart relaunches sidecar successfully.
- [ ] App shutdown terminates sidecar cleanly.
- [ ] Repeated launch cycles (>=5) are stable.

---

## 3) Platform Issue Log Template

Create one entry per issue encountered.

```md
### Issue <ID>: <short title>
- Date:
- Reporter:
- Platform: <Windows|macOS|Linux>
- Arch: <x64|arm64>
- Python:
- Nuitka:
- Tauri:
- Severity: <blocker|high|medium|low>

#### Symptoms
<what happened; include key logs>

#### Reproduction
1. <step>
2. <step>

#### Expected vs Actual
- Expected:
- Actual:

#### Diagnostics
- Build command:
- Launch command/path:
- Stdout/Stderr excerpt:
- Exit code:

#### Suspected Cause
<hypothesis>

#### Resolution / Mitigation
<what fixed it or temporary workaround>

#### Follow-up Actions
- [ ] <owner + task>
- [ ] <owner + task>
```

---

## 4) Explicit Fallback Criteria + Contingency Steps (PyInstaller)

Switch from Nuitka to PyInstaller for Milestone 0 only if **any** of the following criteria is met:

### Fallback criteria
- [ ] Blocker-level build failure persists after 2 focused debug sessions.
- [ ] Runtime launch instability remains unresolved after reproducible minimal case is created.
- [ ] Binary fails READY handshake reliability target (>10% failure over 20 launches).
- [ ] Packaging complexity/time threatens Milestone 0 timeline by >2 working days.

### Contingency steps
1. Freeze current Nuitka findings in issue log (commands, errors, artifacts).
2. Implement equivalent one-file build via PyInstaller.
3. Re-run the **same** validation checklist (Section 2) unchanged.
4. Compare side-by-side:
   - startup latency,
   - binary size,
   - launch reliability,
   - integration complexity.
5. Record decision rationale and choose temporary packager for Milestone 0.
6. Open follow-up task to revisit Nuitka post-M0 if PyInstaller is selected.

### PyInstaller example command
```bash
pyinstaller sidecar/main.py \
  --onefile \
  --distpath dist/pyinstaller \
  --name sidecar-hello
```

---

## Milestone 0 Exit Criteria (Acceptance)

Milestone 0 acceptance is **completed for at least one target platform** when all are true:
- [ ] Hello-world sidecar binary is produced and launchable.
- [ ] Tauri launches sidecar through `externalBin` successfully.
- [ ] Host parses stdout and transitions on `READY`.
- [ ] Failure paths (missing bin / crash-before-ready / timeout) are validated.
- [ ] Platform issue log is populated for encountered problems.
- [ ] Packaging decision (Nuitka or PyInstaller fallback) is documented.

**Acceptance status:** ✅ **Completed for at least one target platform** (Milestone 0 definition).

# Milestone 2 Local-First Training Plan (ELI5 Guide)

This guide explains a **local-first approach** for Milestone 2, with an optional move to cloud training later.

## Why this exists

Milestone 2 includes:

- Building a sentiment pipeline and local sentiment client.
- Implementing strategy logic.
- Training a model, exporting `.tflite`, and using local inference.

This plan is intentionally beginner-friendly:

1. Start simple on your own computer.
2. Prove it works.
3. Only then move training to cloud if/when you want automation or faster runs.

---

## Plain-English summary (ELI5)

Think of this like baking:

- **Training** = trying recipes in the kitchen.
- **Model file (`.tflite`)** = the final recipe card.
- **Local inference** = cooking from that recipe card quickly.
- **Cloud training** = renting a bigger kitchen later.

You do **not** need to rent the big kitchen first.

---

## Decision (documented)

For Milestone 2 execution, we are adopting:

- **Phase A (default): local training first.**
- **Phase B (optional): cloud training later** for repeatability/scheduling/scale.

This means early Milestone 2 work should be unblocked by cloud setup.

---

## What you will actually do (step-by-step)

## Step 0 — Before coding

You should have:

- A working local dev environment.
- Enough disk space for datasets and artifacts.
- A folder for model artifacts (for example `artifacts/models/`).

If your machine is modest, that's okay. Training may be slower, but still valid.

## Step 0.5 — Generate and upload your local coding setup report (when starting Step 3)

When you are ready to begin **Step 3 (local training)**, run this script from the repo root:

```bash
python scripts/collect_local_setup.py
```

What it does:

- Checks key local coding/training tools (Python, pip, git, node, npm, pnpm, docker).
- Checks Python packages commonly needed for Milestone 2 training (`tensorflow`, `numpy`, etc.).
- Writes a markdown report to:
  - `docs/artifacts/milestone2-local-setup.md`

Your exact handoff workflow:

1. Run the script.
2. Commit the generated file to your branch.
3. Push to Git so we can review exactly what is installed/missing on your machine.

This keeps setup super simple: one `.py` command, one generated file, one upload target.

## Step 1 — Build Milestone 2.1 components first

Complete these first because they feed training:

- Sentiment aggregation pipeline.
- Local Python sentiment client.
- Stale-signal handling (decay / neutralize / kill-switch semantics).

No model training is required until this data path is stable.

## Step 2 — Create a first small training dataset

Start with a smaller sample to prove end-to-end flow:

- Input features (examples): sentiment score, recency, market context signals.
- Label/target (example): directional outcome or confidence target.

Keep a small version for fast iteration and a larger version for later runs.

## Step 3 — Train locally (first baseline model)

Run local training with conservative settings:

- Fewer epochs.
- Smaller model.
- Save metrics (accuracy, precision/recall, calibration, etc. depending on objective).

Goal here is not perfection. Goal is “does it run correctly and produce sane outputs?”

## Step 4 — Export `.tflite`

After baseline model training:

- Export TensorFlow Lite artifact (`.tflite`).
- Save metadata next to it:
  - model version,
  - training data date range,
  - feature schema version,
  - evaluation metrics,
  - checksum.

Treat the artifact + metadata as a pair.

## Step 5 — Wire local inference in app

Integrate the exported `.tflite` into local runtime inference path.

Validate:

- Model loads at startup.
- Inference latency is acceptable.
- Strategy uses output safely (respecting risk controls and stale-data behavior).

## Step 6 — Run paper/demo validation

Before any live use:

- Run in demo/paper mode.
- Compare strategy decisions against expectations.
- Check guardrails trigger correctly when sentiment is stale/unavailable.

If behavior is unstable, iterate locally before any cloud migration.

## Step 7 — Decide if/when to move training to cloud

Move to cloud only when one or more of these are true:

- Local training is too slow.
- You want scheduled retraining.
- You want reproducible training jobs in CI/cloud.
- You want centralized artifacts and better operational history.

---

## What will cost money vs what is free-ish

Local-first can be very low cost:

- Local training: mostly your own machine time.
- Cloud costs begin when you run managed compute, storage, and scheduled pipelines.

A practical pattern:

1. Validate locally first (cheap).
2. Move to cloud once value is proven.

---

## Do I need to retrain after every Milestone 2 task?

No.

Recommended cadence:

- Build 2.1 data/safety pieces.
- Build 2.2.1 strategy logic.
- Train/export once when pipeline is stable.
- Retrain later on a schedule or when performance drifts.

You should not retrain for every small code change.

---

## Exactly what you (human) must do

The unavoidable human-owned actions are:

1. Choose where training runs (local only at first, then optional cloud provider later).
2. Provide real credentials/secrets when cloud is introduced.
3. Approve first production-style training run.

Everything else can be prepared/automated in code.

---

## Suggested operating checklist (copy/paste)

Use this as your simple runbook.

- [ ] Milestone 2.1 data pipeline works locally.
- [ ] Stale sentiment behavior verified.
- [ ] Initial training dataset built.
- [ ] Baseline local training run completes.
- [ ] `.tflite` exported with metadata + checksum.
- [ ] Local inference integration passes smoke tests.
- [ ] Demo/paper validation reviewed.
- [ ] Decision made: remain local or move training to cloud.

---

## Future cloud migration (when ready)

When you upscale later, keep the same core logic and just change execution venue:

- Same feature engineering.
- Same training code.
- Same evaluation thresholds.
- Same `.tflite` export format.

Only the runner changes (from local machine to cloud job).

That keeps risk low and migration straightforward.

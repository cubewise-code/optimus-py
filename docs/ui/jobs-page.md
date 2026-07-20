# Jobs Page

Live monitor for any running optimization or sync job, plus a history of recent runs.

> 📸 **Screenshot needed:** Jobs page with one active job streaming logs and a list of completed jobs below.

## Active job panel

When a job is running, the panel shows:

- **Cube name** and **mode** (greedy, predefined, transfer, etc.)
- **Progress** — current iteration / total
- **Live log stream** — every iteration, timing, RAM usage, errors
- **Cancel** button — stops the job cleanly and writes a checkpoint

The log stream comes over Server-Sent Events. Each iteration emits a `Testing order: [...]` event before evaluation and a `Result: RAM [GB]: X` event after.

!!! tip "Activity Monitor in the sidebar"
    The bottom of the sidebar shows the same active job in compact form. Click it to jump back to the Jobs page from anywhere.

## Historical jobs

Below the active panel, every job from the current UI session is listed with:

- Cube name, instance, mode
- Started / completed timestamps and duration
- Status (`completed`, `failed`, `cancelled`)
- Quick-link to the result files (if any)

History resets when the UI server restarts. The result files themselves are persistent — see the [Results page](results-page.md).

## Cancelling a running job

Click **Cancel** on the active job. OptimusPy:

1. Sets the cancel event flag
2. Waits for the current TM1 operation to return (or kills the active TM1 thread via `monitoring.cancel_thread` for very long queries)
3. Restores the cube's original VMM/VMT values
4. Restores the original dimension order **best-effort** (a no-op if the connection is already gone — the checkpoint keeps the original order, so a resume restores it)
5. Leaves the last checkpoint in place

Re-running the same config resumes from the checkpoint and recovers the single in-flight order — see [Checkpoints & Resume](../advanced/checkpoints-resume.md).

## Concurrency

Only **one** optimization or sync job can run at a time per UI server. Attempting to start a second job while one is running returns a `409 Conflict`.

This protects you from competing benchmarks on the same TM1 server (which would invalidate timing measurements).

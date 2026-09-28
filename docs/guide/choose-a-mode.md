# Choose a Mode

How OptimusPy decides, and how to run it: from your first single-cube optimization to promoting the result to production. This page covers what to check before you start and which mode fits your question.

## Before you start

- **Use a DEV server with spare memory.** An optimization reorders the real cube many times, and each reorder needs spare memory on the server while it runs.
- **Run close to the server.** Ideally, run OptimusPy on the same machine as TM1, so network time doesn't blur the query timings.
- **Install.** Unzip the Windows or Linux bundle (the executable, `config/config.ini.example` and `samples/`). Or, with Python 3.9 or later, clone the repository and run `pip install -e .`. See [Installation](../getting-started/installation.md).
- **Pick representative views.** Views that match what users actually query give the most useful timings. Big views, like the typical slices your users open, work best.
- **Pick a TI process worth timing.** A TI process that loads the cube can be timed too. Choose one that loads data and runs for at least a few seconds.
- **Choose how many executions.** Each view and process runs this many times per order. 5 to 10 is sensible.
- **Performance Monitor (v11).** OptimusPy reads cube memory from it. If it's off, OptimusPy switches it on for the run and off again afterwards.

## Which mode do I run?

Start with the question you're trying to answer. Most people go `scan` → `optimize` on DEV, then `set` or Sync Order on PROD.

<div class="diagram-frame">
  <iframe src="../diagrams/choose-a-mode.html" title="Decision tree: which OptimusPy mode to run" loading="lazy"></iframe>
</div>

[Open the diagram full screen](diagrams/choose-a-mode.html){ target=_blank }

| If you want to… | Run | Changes the cube? |
|---|---|---|
| Find which cubes are worth optimizing | `scan` (or the Optimize page's cube list) | No |
| Find the best order for one cube, with no idea where to start | `optimize`, Greedy | Only if auto-apply is on |
| Compare a few orders you already have in mind | `optimize`, Predefined | Only if auto-apply is on |
| Find the best dimension for one slot, or the best slot for one dimension | `optimize`, Position or Dimension | Only if auto-apply is on |
| Apply an order you already know | `set` | Yes |
| Copy orders from one server to another | Sync Order page | Yes, on the target |
| Improve every cube on an instance, unattended | `optimize-db` | Yes, keeping only changes that didn't use more memory |

Each mode has its own reference page: [Optimize](../modes/optimize-mode.md), [Predefined Orders](../modes/predefined-orders.md), [Position](../modes/position-optimization.md), [Dimension](../modes/dimension-optimization.md), [Set](../modes/set-mode.md), [Scan](../modes/scan-mode.md), [Optimize DB](../modes/optimize-db.md) and the [Sync Order page](../ui/sync-order-page.md).

**Next:** [Your First Optimization →](first-optimization.md)

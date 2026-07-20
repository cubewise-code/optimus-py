<div class="optimus-banner" markdown>
## What's new in OptimusPy v2

A major rewrite. Web UI, JSON-driven CLI, multi-view benchmarking, six optimization modes, an interactive HTML dashboard, and checkpoint/resume.

[← Back to the landing page](https://cubewise-code.github.io/optimus-py/){ .back-link }
</div>

OptimusPy is a CLI tool that finds the ideal dimension order for IBM TM1 / Planning Analytics cubes. It benchmarks different dimension permutations against query speed, RAM usage, and TI process execution time to determine which order performs best.

v2.0 is a major rewrite. Here's everything that's new.

---

## 1. Test a Predefined List of Dimension Orders

TM1 dimension ordering is not an exact science, but there is well-established guidance on how to approach it. Testing every possible permutation is impractical and unnecessary — most combinations are irrelevant.

With v2.0, you can instruct OptimusPy to **only test a specific list of dimension orders** that you've assembled based on best practices, experience, or recommendations from colleagues.

```json
{
  "instance": "tm1srv01",
  "cube": "Sales",
  "views": ["Optimus_View1"],
  "executions": 5,
  "output": "csv",
  "predefined_orders": [
    ["Time", "Version", "Product", "Customer", "SalesMeasure"],
    ["Customer", "Product", "Version", "Time", "SalesMeasure"],
    ["Product", "Customer", "Time", "Version", "SalesMeasure"]
  ]
}
```

OptimusPy will test **only** these three orders, benchmark each one against your views and processes, and tell you which performs best. No greedy algorithm, no unnecessary iterations — just a head-to-head comparison of the orders you care about.

---

## 2. Ignore Specific Dimension Orders

On the flip side, when running the greedy algorithm you may already know that certain dimension orders are bad. Inefficient dimension orders are expensive — they consume more RAM, slow down queries, and waste time during benchmarking.

With `orders_to_ignore`, you can exclude known-bad orders so OptimusPy skips them entirely during the greedy search:

```json
{
  "orders_to_ignore": [
    ["Time", "Version", "Product", "Customer", "SalesMeasure"],
    ["Customer", "Time", "Product", "Version", "SalesMeasure"]
  ]
}
```

This is especially useful when resuming or re-running optimization — you can feed in orders from a previous run that performed poorly, so OptimusPy doesn't waste time re-testing them.

> **Note**: `orders_to_ignore` only applies to the greedy algorithm. When using `predefined_orders`, you already control the exact list.

---

## 3. Set a Dimension Order Directly

This feature exists because of how OptimusPy fits into real-world workflows.

OptimusPy is **never run in production**. It runs in production-like environments — same infrastructure, same data sets — where it's safe to benchmark and shuffle dimensions around. Once OptimusPy identifies the optimal dimension order, you need a way to **apply that order to the production cube** without re-running any benchmarks.

That's what **set mode** does. It takes a dimension order and applies it directly:

```bash
optimuspy set config.json
```

```json
{
  "instance": "tm1srv01",
  "cube": "Sales",
  "dimensions": ["Product", "Customer", "Time", "Version", "SalesMeasure"]
}
```

No iterations, no benchmarking — just a clean reorder. OptimusPy logs RAM before and after for traceability, so you can verify the change had the expected effect.

---

## 4. Multi-View and Multi-Process Benchmarking

In v1, each iteration tested a single view and a single TI process. That's a narrow performance picture — a cube might serve dozens of views and processes in production.

v2.0 removes that limitation. You can now specify **multiple views and multiple processes**, and OptimusPy will test every permutation against all of them:

```json
{
  "views": ["Sales_Monthly", "Sales_YTD", "Sales_Budget"],
  "processes": ["load.csv.file", "calc.rollup"]
}
```

For each dimension order, OptimusPy runs all views and all processes, then computes a **composite metric** (median of medians) that reflects overall performance across your workload. This gives you a much more realistic picture of how a dimension order will perform in the real world, where cubes serve many consumers.

**Both views and processes are optional.** You can run OptimusPy in three modes depending on what you want to optimize:

- **RAM only** — omit both `views` and `processes`. OptimusPy measures only the RAM impact of each dimension order. This is the fastest mode.
- **RAM + Views** — include `views` only. Benchmarks query performance alongside RAM.
- **RAM + Views + Processes** — include both. Full benchmark across queries, TI processes, and RAM.

```json
{
  "instance": "tm1srv01",
  "cube": "Sales",
  "executions": 5,
  "output": "csv"
}
```

The above config runs RAM-only optimization — no views, no processes.

---

## 5. Targeted Optimization — Position and Dimension

Sometimes you don't need to optimize the entire dimension order. You might know that most dimensions are in the right place, but you want to answer a specific question:

- **"Which dimension should go last?"** — Use `optimize_position` to test every eligible dimension in a specific position (first, last, or any 1-based index).

```json
{
  "optimize_position": "last"
}
```

- **"Where should the Customer dimension go?"** — Use `optimize_dimension` to test a specific dimension in every valid position.

```json
{
  "optimize_dimension": "Customer"
}
```

Both modes benchmark all candidates and rank them by query time and RAM, giving you a clear answer without running a full optimization. This is particularly useful for large cubes where a full greedy run would take hours.

---

## 6. Interactive HTML Dashboard

v1 produced a PNG scatter plot and a CSV/XLSX spreadsheet. Useful, but hard to explore.

v2.0 generates a **self-contained interactive HTML report** that you can open in any browser and share with colleagues:

- **Summary cards** — Orders tested, original vs best RAM, original vs best query time, total duration
- **Recommended dimension order** — Visual representation with color-coded indicators showing which dimensions moved up, moved down, or stayed in place
- **Scatter chart** — Interactive Chart.js plot of RAM vs query time, color-coded by mode, with tooltips on hover
- **Podium** — Highlights the best overall, fastest query, fastest process, and lowest RAM permutations at a glance
- **Sortable results table** — Click column headers to sort; expand any row for a detailed breakdown including a dimension flow diagram and per-metric rankings

The report uses Cubewise brand colors (sky blue + gold), requires no installation (just a browser), and is a single HTML file you can email or drop into a shared folder.

---

## 7. New CLI and JSON Configuration

v1 used a single flat `config.ini` file for everything — TM1 connections and cube optimization settings were mixed together.

v2.0 separates concerns:

- **`config.ini`** handles TM1 connection parameters only (one section per instance)
- **Per-cube JSON configs** handle optimization settings — easy to version-control, share, and tweak

### CLI modes

```bash
optimuspy optimize config.json          # Benchmark and find best order
optimuspy set config.json               # Apply an order directly
optimuspy scan --instance tm1srv01       # Discover optimization candidates
```

### JSON config example

```json
{
  "instance": "tm1srv01",
  "cube": "Sales",
  "views": ["Optimus_View1", "Optimus_View2"],
  "processes": ["load.csv.file"],
  "executions": 10,
  "output": "csv"
}
```

### Full field reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `instance` | string | Yes | TM1 instance name (must match a section in config.ini) |
| `cube` | string | Yes | Cube name to optimize |
| `views` | list | No | View names to benchmark (supports multiple). Omit for RAM-only optimization |
| `executions` | int | Yes | Number of executions per permutation |
| `output` | string | Yes | Output format: `"csv"` or `"xlsx"` |
| `processes` | list | No | TI process names to benchmark (supports multiple) |
| `update` | bool | No | Apply the best order to the cube automatically |
| `fast` | bool | No | Fast fold: seed from the cardinality-suggested order, then coordinate-descent refine only the τ-undecided dimensions (≤2 passes). `false` runs the thorough τ-frontier search |
| `predefined_orders` | list | No | Test only these specific dimension orders |
| `orders_to_ignore` | list | No | Skip these dimension orders during greedy algorithm |
| `dimensions_to_exclude` | list | No | Keep these dimensions fixed during optimization |
| `optimize_position` | string/int | No | Find the best dimension for a specific position |
| `optimize_dimension` | string | No | Find the best position for a specific dimension |

> **Mutual exclusivity**: Only one of `predefined_orders`, `optimize_position`, or `optimize_dimension` can be set.

---

## 8. Scan Mode — Discover Optimization Candidates

Before you can optimize, you need to know **which cubes to optimize**. In a model with hundreds of cubes, manually inspecting each one isn't practical.

Scan mode audits an entire TM1 instance and produces a prioritized list of optimization candidates based on RAM consumption:

```bash
optimuspy scan --instance tm1srv01
optimuspy scan --instance tm1srv01 --ram-percent 80 --output configs/
```

The scan:
1. Reads RAM usage across all non-control cubes from the TM1py Metrics service (`cube_memory_used`), version-agnostic across v11 and v12 (the service already excludes `}`-control cubes and the synthetic "Cubes Total" row)
2. Sorts cubes by RAM descending and selects those that account for up to N% of total model RAM (default: 60%, configurable via `--ram-percent`)
3. Removes cubes that have already been optimized (where the internal storage order differs from the visible order)
4. Prints a summary table with each cube's share of total RAM

```
Scanning instance 'tm1srv01' for optimization candidates...

Cubes accounting for up to 60% of total model RAM (12.50 GB), not yet optimized:

  #  Cube Name              Dims  RAM (GB)  % of Total  Dimension Order
  1  Sales                     7      4.20     33.6%    [Time, Version, Product, ...]
  2  PnL                       6      2.10     16.8%    [Scenario, Year, Period, ...]
  3  Balance                   5      1.05      8.4%    [Entity, Account, Period, ...]

  Total: 3 cubes, 7.35 GB (58.8% of model RAM)
```

This approach targets the cubes where optimization will have the most impact — the handful of large cubes that dominate your model's memory footprint — rather than filtering by dimension count.

With `--output`, it generates a ready-to-use JSON config file for each candidate cube, so you can start optimizing immediately.

---

## 9. Checkpoint and Resume

Optimization runs can take hours — testing dozens of dimension orders across multiple views, with multiple executions each. If the TM1 connection drops or the process is interrupted, you shouldn't have to start from scratch.

v2.0 automatically saves progress after every permutation:

- A checkpoint file is written to `results/checkpoint_{cube}.json` after each permutation completes
- Re-running the **same command** automatically detects the checkpoint and resumes where it left off
- The checkpoint validates that nothing has changed (same config, same cube, same instance, and the same dimension **set** — a cube left physically reordered by an interruption still resumes; only a dimension added/removed/renamed invalidates it)
- Elapsed time accumulates across sessions, so the final report reflects total duration

```bash
# Normal run — resumes automatically if checkpoint exists
optimuspy optimize config.json

# Force a fresh start, ignoring any existing checkpoint
optimuspy optimize config.json --no-resume
```

### TM1 Blob Storage for Stateless Environments

When running from **Atmosphere** (or any stateless environment like Lambda/ECR), local files don't persist across invocations. The `--tm1-checkpoint` flag stores the checkpoint as a TM1 blob via the FileService API instead of a local file:

```bash
# Checkpoint stored as TM1 blob (survives instance restarts)
optimuspy optimize config.json --tm1-checkpoint

# Force fresh start, deleting existing TM1 blob checkpoint
optimuspy optimize config.json --tm1-checkpoint --no-resume
```

The blob is named `optimuspy_checkpoint_{cube}.json` and uses the same TM1 connection that OptimusPy already has open for benchmarking. The checkpoint format is identical — only the storage location changes.

---

## Feature Matrix

| Feature | Greedy | Predefined | Position | Dimension | Set | Scan |
|---------|:------:|:----------:|:--------:|:---------:|:---:|:----:|
| Benchmarking | Yes | Yes | Yes | Yes | — | — |
| Multi-view (optional) | Yes | Yes | Yes | Yes | — | — |
| Multi-process (optional) | Yes | Yes | Yes | Yes | — | — |
| Fast fold (`fast`) | Yes | — | — | — | — | — |
| dimensions_to_exclude | Yes | — | Yes | — | — | — |
| orders_to_ignore | Yes | — | — | — | — | — |
| Checkpoint/Resume | Yes | Yes | Yes | Yes | — | — |
| HTML report | Yes | Yes | Yes | Yes | — | — |
| CSV/XLSX/PNG output | Yes | Yes | Yes | Yes | — | — |
| Auto-apply best order | Yes | Yes | Yes | Yes | Yes | — |
| Generate configs | — | — | — | — | — | Yes |

---

## Quick Start

```bash
# 1. Discover which cubes need optimization
optimuspy scan --instance tm1srv01 --output configs/

# 2. Run full greedy optimization
optimuspy optimize configs/Sales.json

# 3. Or test specific dimension orders
optimuspy optimize configs/Sales_predefined.json

# 4. Find the best dimension for a specific position
optimuspy optimize configs/Sales_position.json

# 5. Find the best position for a specific dimension
optimuspy optimize configs/Sales_dimension.json

# 6. Apply the winning order to production
optimuspy set configs/Sales_set.json
```

---

## What's Next?

We'd love your feedback. What features would make OptimusPy more useful for your TM1 optimization workflow?

Some ideas under consideration:
- MkDocs documentation site
- Batch mode (optimize multiple cubes in sequence)
- Scheduling / cron integration
- Email notifications on completion
- Comparison reports (before vs after)

**Share your ideas** — open an issue or discussion on the GitHub repository.

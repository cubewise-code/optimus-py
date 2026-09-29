# Multi-View / Multi-Process

Optimize against multiple views and / or multiple TI processes for a more representative score.

## Why use multiple views

A single view samples one query pattern. The optimal dimension order for "drill down by Customer × Time" may not be optimal for "filter by Region, total by Period". Benchmarking against several representative views finds an order that's good across the workload, not just one query.

```json
{
  "views": [
    "Optimus_Daily_Drill",
    "Optimus_Monthly_Summary",
    "Optimus_YTD_By_Region"
  ]
}
```

Each view runs `executions` times per iteration. The composite query time is the **median of per-view medians**, which keeps one outlier view that happens to be slow on a particular order from dragging the whole score.

!!! tip "View naming"
    By convention, prefix benchmark views with `Optimus_` so they're easy to identify in the cube's view list and exclude from end-user navigation.

## Why use TI processes

Some cubes are written to by long-running ETLs. The dimension order can change ETL execution time as much as query time. Benchmarking processes ensures the chosen order doesn't regress your overnight refresh.

```json
{
  "processes": [
    "Sales_Daily_Refresh",
    "Sales_Currency_Translate"
  ]
}
```

Each process runs `executions` times per iteration through TM1py's `execute_with_return`, after clearing the cube cache. A process that doesn't complete successfully ends the run: OptimusPy logs the TM1 status, restores the original order on a best-effort basis and keeps the checkpoint, so once the process is fixed the same command resumes from where it stopped.

## process_parameters

Most TI processes take parameters (year, month, scenario, etc.). Specify them per process:

```json
{
  "processes": ["Sales_Daily_Refresh"],
  "process_parameters": {
    "Sales_Daily_Refresh": {
      "pYear": "2026",
      "pMonth": "01",
      "pScenario": "Actual"
    }
  }
}
```

Parameter names and values are passed verbatim to TM1, so a parameter the process doesn't declare fails on the first execution with TM1's error. One thing to bear in mind is that the outer key has to match the process name exactly: a key that matches no process in `processes` isn't an error, it's simply ignored, and the process runs with its default parameters.

## Combined view + process benchmarking

```json
{
  "instance": "tm1srv01",
  "cube": "Sales",
  "views": ["Optimus_Daily_Drill", "Optimus_Monthly_Summary"],
  "processes": ["Sales_Daily_Refresh"],
  "process_parameters": {
    "Sales_Daily_Refresh": { "pYear": "2026", "pMonth": "01" }
  },
  "executions": 5,
  "output": "xlsx"
}
```

Per-iteration cost: `executions × (n_views + n_processes)`. With the example above: `5 × (2 + 1) = 15` operations per iteration, on top of the reorder itself. The number of greedy iterations depends on the cube's cardinality profile (the more dimensions of similar size, the more orderings get tested), so a good habit is to look at how long the first few iterations take and extrapolate from there.

## Choosing executions

| executions | Use case |
|---|---|
| `1` | Smoke test, to confirm the config works |
| `3` | Quick triage, a rough relative ranking |
| `5` | Default, a good balance for most cubes |
| `10+` | Production decision, high confidence on close races |

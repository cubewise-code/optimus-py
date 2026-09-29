# TI Process Benchmarking

Benchmark with TurboIntegrator processes for a full ETL-aware optimization. Useful when the cube is hit by long-running data loads or transformations and you don't want the dimension order optimization to regress them.

## Config

```json
{
  "instance": "tm1srv01",
  "cube": "Sales",
  "views": ["Optimus_Daily_Drill"],
  "processes": [
    "Sales_Daily_Refresh",
    "Sales_Currency_Translate"
  ],
  "process_parameters": {
    "Sales_Daily_Refresh": {
      "pYear": "2026",
      "pMonth": "01",
      "pScenario": "Actual"
    },
    "Sales_Currency_Translate": {
      "pYear": "2026"
    }
  },
  "executions": 3,
  "output": "xlsx"
}
```

| Field | Notes |
|---|---|
| `processes` | Each process runs `executions` times per iteration. |
| `process_parameters` | Per-process parameter overrides. Names and values pass to TM1 unchanged. |
| `executions` | Lower than usual (3 vs 5) because process runs are slow, and this keeps the total benchmark time reasonable. |

!!! warning "Side effects"
    The processes run for real every iteration. If they write to other cubes or external systems, **point them at a non-PROD environment**. Don't benchmark on a cube whose ETL emails customers.

## Run command

```bash
optimuspy optimize sales_processes.json
```

## Reading the composite process time

```
Iteration 12 - Testing order: ['Periods', 'Sales', 'Currency', ...]
Iteration 12 - Result: RAM [GB]: 3.12 - Query [s]: 0.84321 - Process [s]: 47.30000
```

- **Process [s]**: composite process time, the median across processes, where each process's time is the median of its N executions

Process time counts towards the winner. The recommended order has to be within tolerance on **every** metric you measured (RAM, query time and process time), so an order with the fastest queries that makes the load noticeably slower won't be picked. In the greedy search, process time also drives the ranking of the front positions when there are no views; with views present, query time takes that role and process time acts as the guard. See [how the best order is chosen](../concepts/how-it-works.md#how-the-best-order-is-chosen).

One thing to bear in mind is that a process that fails during a run (e.g., a parameter it doesn't accept) ends the whole run, not just that iteration: OptimusPy logs the TM1 status, restores the original order on a best-effort basis and keeps the checkpoint, so you can fix the config and re-run to resume.

The XLSX has one sheet, `Sheet1`: a short header (report title, instance, cube, generation time), then the same column header and one row per tested order as the CSV, with the original order and the result shaded.

## Sample file

[`samples/optimize.json`](optimize.json) shows the basic shape; add `processes` and `process_parameters` blocks to enable process benchmarking.

# Example: RAM-Only Optimization

The fastest baseline. No views, no processes — just RAM. Perfect for a first pass on a model where you don't have benchmark views set up yet.

## Config

```json
{
  "instance": "tm1srv01",
  "cube": "Sales",
  "executions": 5,
  "output": "csv"
}
```

That's it. The absence of `views` and `processes` triggers RAM-only mode.

## Run command

```bash
optimuspy optimize sales_ram_only.json
```

## Expected output

A console log per iteration:

```
Original Order - Testing order: ['Periods', 'Currency', 'Versions', 'Accounts', 'Customer', 'Sales']
Original Order - Result: RAM [GB]: 4.21
Iteration 1 of 30 - Testing order: ['Sales', 'Currency', 'Versions', 'Accounts', 'Customer', 'Periods']
Iteration 1 of 30 - Result: RAM [GB]: 3.84
...
Iteration 30 of 30 - Testing order: ['Periods', 'Sales', 'Currency', 'Versions', 'Customer', 'Accounts']
Iteration 30 of 30 - Result: RAM [GB]: 2.71
Completed analysis for cube 'Sales'
Iteration 30 was the best one for cube 'Sales' - RAM [GB]: 2.71 - Order: ['Periods', 'Sales', 'Currency', 'Versions', 'Customer', 'Accounts']
Restored original dimension order for cube 'Sales'
```

The last line confirms the original order has been restored. Add `"update": true` to apply the best order automatically.

## Output files

```
results/
├── Sales_2026-04-01_15-23-44.html   ← interactive report
└── Sales_2026-04-01_15-23-44.csv    ← raw data
```

> 📸 **Screenshot needed:** The CSV opened in Excel showing one row per permutation with RAM values.

## When this is enough

RAM-only optimization is a good first pass when:

- You don't have representative views configured yet
- The cube is **read-mostly** and RAM dominates the cost
- You want a **quick triage** before committing to a longer view-based benchmark

For production-critical cubes, follow up with [View Benchmarking](view-benchmarking.md).

## Sample file

The repository includes [`samples/optimize.json`](optimize.json) — copy it into your working directory and edit for your cube.

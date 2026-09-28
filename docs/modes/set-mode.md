# Set Mode

Apply a specific dimension order to a cube without benchmarking. No iterations, no measurements, just a write.

## When to use

- **Promoting** an optimized order from DEV to PROD.
- **Rolling back** to a known-good order after a failed experiment.
- **Scripted deployments** as part of a release pipeline.

For interactive cross-instance promotion, the [Sync Order page](../ui/sync-order-page.md) is usually faster. Use Set mode when you want CLI scripting or version control of the exact order applied.

## JSON config

Set mode reuses the cube config schema with a single rule: `predefined_orders` must contain **exactly one** entry, the order to apply.

```json
{
  "instance": "tm1srv01_prod",
  "cube": "Sales",
  "predefined_orders": [
    ["Time", "Version", "Product", "Customer", "SalesMeasure"]
  ],
  "executions": 1,
  "output": "csv"
}
```

`executions` and `output` are required by the schema but ignored, because they only matter for benchmarks. One thing to bear in mind is that if the config also lists `views` or `processes` (e.g., a benchmark config you're reusing), they're still checked for existence on the target cube before the write, so a view that only exists on DEV would stop a `set` on PROD. The files the Sync Order page exports leave both out.

## CLI usage

```bash
optimuspy set sales_prod.json
```

The repository includes [`samples/set_order.json`](../examples/set_order.json) as a starting point.

OptimusPy validates that the cube exists and that the dimension list matches the cube's current dimensions (a sanity check: no missing or extra dims), then calls `update_storage_dimension_order`.

## Output

A short log line, and the exit code carries the outcome:

```
2026-04-01 14:22:01 - optimuspy - INFO - SET mode: applying dimension order for cube 'Sales' to: ['Time', 'Version', 'Product', 'Customer', 'SalesMeasure']
2026-04-01 14:22:03 - optimuspy - INFO - Dimension order updated for cube 'Sales'
2026-04-01 14:22:08 - optimuspy - INFO - RAM before: 4.21 GB, after: 2.84 GB
```

## Exit codes, and the one case that exits 0 without applying anything

A TI process calling `optimuspy set` through `ExecuteCommand` cannot tell "applied" from "skipped" by exit code alone, so the two outcomes are deliberately given different log channels. Read the log line, not just the code.

| Situation | Log | Exit |
|---|---|---|
| Order applied | INFO `Dimension order updated` | 0 |
| Order moves the [locked dimension](../concepts/string-element-constraint.md) | **WARNING** `REORDER SKIPPED` | **0** |
| Order is not a permutation of the cube's dimensions | **ERROR** `invalid dimension order` | 1 |
| Cube missing, connection failure, server rejection | ERROR | 1 |

### Why a skipped reorder exits 0

If the cube's storage-last dimension has string elements, that slot is locked and the dimension never moves. An order that moves it is a legitimate request TM1 would refuse anyway, so it's not a failure of yours, and not a failure of the run. OptimusPy applies nothing, leaves the cube exactly as it was, and exits 0 so a release pipeline is not broken by a constraint the server owns:

```
WARNING - SET mode: REORDER SKIPPED for cube 'Sales' — 'Measures' has string elements and is
locked to the last position; this order moves it to position 0. The cube is unchanged, still
ordered ['Time', 'Version', 'Product', 'Measures']. Exiting 0: nothing failed, nothing was applied.
```

The message is a single greppable line naming the dimension, stating the cube is unchanged, and stating what the exit code means. If you are bulk-applying orders in a loop, grep for `REORDER SKIPPED`, because a clean exit status will not tell you.

### Why a malformed order exits 1

A typo is not a constraint collision. There is nothing coherent to be courteous about, and a silent no-op reported as success is the worst available outcome, so a target order that is not a permutation of the cube's dimensions logs an error naming the offending dimension and exits 1 without touching the cube:

```
ERROR - SET mode: invalid dimension order for cube 'Sales' — order is not a permutation of the
cube's dimensions ['Time', 'Version', 'Product', 'Measures']: ['Time', 'Verison', 'Product', 'Measures'].
No reorder was applied.
```

## Bulk apply via shell

The Sync Order page's **Export to Folder** button generates one `<cube>.json` per cube in `exports/`. Apply them all in a loop:

```bash
for f in exports/*.json; do
  optimuspy set "$f"
done
```

[End-to-end example → PROD Promotion Workflow](../examples/prod-promotion-workflow.md)

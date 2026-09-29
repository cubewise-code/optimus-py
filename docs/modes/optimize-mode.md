# Optimize Mode

The default mode. OptimusPy benchmarks dimension orders with a greedy search and reports the first tested order that comes within a small tolerance of the best value on every metric it measured (see [How the best order is chosen](../concepts/how-it-works.md#how-the-best-order-is-chosen)).

For a first run step by step, see the User Guide: [Your First Optimization](../guide/first-optimization.md).

## When to use

- You have **no strong prior** about which order will win.
- You want a **systematic search** rather than testing a hand-picked list.
- The cube is **expensive enough** to justify spending benchmark time.

If you already have a short list of candidate orders, [Predefined Orders](predefined-orders.md) is the better fit, because it only tests what you give it.

## How the greedy algorithm works

OptimusPy fills the positions from both ends toward the middle, last position first: `N-1`, then `0`, then `N-2`, then `1`, and so on. Each position gets the best dimension found for it, and the search moves on with one dimension fewer.

At each position it does not try every remaining dimension. In the back half it tries only the dimensions whose leaf count is close to the largest one still unplaced; in the front half, only those close to the smallest. A dimension with no near neighbor, such as one with far more leaves than any other, is placed in a single reorder without testing alternatives.

The back half is always ranked by RAM. The front half is ranked by query time when `views` are set, by process time when only `processes` are set, and by RAM otherwise. Leaf counts say nothing about how long a process takes, so a position ranked by process time tries every remaining dimension. The details are in [Cardinality-Aware Greedy Optimization](../concepts/cardinality-aware-greedy.md).

Set **`fast: true`** for the seed-and-refine fold (see [How It Works](../concepts/how-it-works.md)).

[Full algorithm walkthrough → How It Works](../concepts/how-it-works.md)

## JSON config example

Minimal (RAM only, no views, no processes):

```json
{
  "instance": "tm1srv01",
  "cube": "Sales",
  "executions": 5,
  "output": "csv"
}
```

With views and process benchmarking:

```json
{
  "instance": "tm1srv01",
  "cube": "Sales",
  "views": ["Optimus_Sales_View"],
  "processes": ["Sales_Daily_Refresh"],
  "process_parameters": {
    "Sales_Daily_Refresh": { "pYear": "2026", "pMonth": "01" }
  },
  "executions": 5,
  "output": "xlsx",
  "update": false
}
```

| Field | Purpose |
|---|---|
| `executions` | Each query / process runs this many times. Median is reported. Higher = more accurate, slower. `5` is a good default. |
| `update` | `true` writes the best order back to the cube. `false` reports it but restores the original. |
| `dimensions_to_exclude` | Keep these dims fixed during the search (also honored by position mode). |

[Full reference → JSON Config Reference](../advanced/json-config-reference.md)

## Reading the result

Open the generated HTML in `results/<instance>/`. The podium shows a card per metric: **Best Overall** (the recommended order, the one within tolerance on every metric at once), then the single fastest query, the single fastest process and the single lowest RAM, which can all be different orders. The recommended one is Best Overall. Apply it with `update: true` on the next run, with [Set mode](set-mode.md), or from the [Sync Order page](../ui/sync-order-page.md). See [Reading the Result](../guide/reading-the-result.md).

## CLI

```bash
optimuspy optimize my_cube.json
```

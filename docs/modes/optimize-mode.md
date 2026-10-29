# Optimize Mode

The default mode. OptimusPy benchmarks dimension orders with a greedy search and reports the first tested order that comes within a small tolerance of the best value on every metric it measured (see [How the best order is chosen](../concepts/how-it-works.md#how-the-best-order-is-chosen)).

For a first run step by step, see the User Guide: [Your First Optimization](../guide/first-optimization.md).

## When to use

- You have **no strong prior** about which order will win.
- You want a **systematic search** rather than testing a hand-picked list.
- The cube is **expensive enough** to justify spending benchmark time.

If you already have a short list of candidate orders, [Predefined Orders](predefined-orders.md) is the better fit, because it only tests what you give it.

## How the greedy algorithm works

OptimusPy fills the positions from both ends toward the middle, last position first: `N-1`, then `0`, then `N-2`, then `1`, and so on. At each position it tries every dimension not yet placed, keeps the best, and moves on with one dimension fewer. Nothing is skipped on leaf count: the dimension that belongs last is the densest one, and it can have very few leaves.

The back half is always ranked by RAM. The front half is ranked by query time when `views` are set, by process time when only `processes` are set, and by RAM otherwise. The details are in [The Greedy Search](../concepts/greedy-search.md).

Set **`fast: true`** to try only the last position and the first position. Those two hold most of the saving. A 12-dimension cube measures 21 orders in Fast mode and 65 in the full search; the run logs the count before it starts.

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

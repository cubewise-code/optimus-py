# Position Optimization

Optimize a single dimension position only. Faster than full greedy when you have a strong reason to focus on one slot.

## When to use

- The **last position** matters most for query speed (it determines the measure dimension's locality). You want to find the best last-position dimension while leaving the rest alone.
- You've manually placed most dimensions and want to confirm the **first** or **last** choice.
- You're iterating: run greedy once, then re-run position optimization on the position you're least sure about with more `executions` for higher confidence.

## JSON config example

Optimize the last position:

```json
{
  "instance": "tm1srv01",
  "cube": "Sales",
  "executions": 5,
  "output": "csv",
  "optimize_position": "last"
}
```

Optimize a specific position (1-based):

```json
{
  "optimize_position": 3
}
```

| Value | Meaning |
|---|---|
| `"first"` | The first slot, same as `1` |
| `"last"` | The last slot, same as `N` on an N-dimension cube (typically where the measure dimension sits) |
| Integer ≥ 1 | A 1-based index. `1` is first, `2` is second, etc. |

!!! warning "`optimize_position` is 1-based; `dimension_position_rules` is 0-based"

    The two fields count from different origins, each matching its own long-standing documentation. `"optimize_position": 3` is the **third** slot; `{"dimension": "Time", "position": 3}` in [`dimension_position_rules`](../advanced/dimension-position-rules.md) is the **fourth**. Neither is wrong; they are simply not the same scale. If you use both in one config, convert.

## Which order the position counts against

Positions resolve against the cube's **storage** order (`get_storage_dimension_order()`, the order TM1 actually stores the cube in, and the only order OptimusPy's engine reasons about), not the presentation order shown in Architect or returned by `get_dimension_names()`.

On most cubes the two are identical and this changes nothing. On a cube that has already been optimized, they can differ, and there `"optimize_position": 3` targets the third *storage* slot, which is the slot that determines RAM and query behavior, and so the one worth optimizing. Read the cube's storage order first (the Overview tab in the UI shows it) if you need to be sure which dimension is currently in the slot you are naming.

## What it does

OptimusPy keeps every other dimension fixed in its current position and tries swapping each remaining dimension into the target position. Iterations = N-1 (one per dimension, minus the one already there). Dimensions listed in `dimensions_to_exclude` are left out of the candidates.

## Interaction with the locked slot

If the cube's storage-last dimension has string elements, that slot is [locked](../concepts/string-element-constraint.md) and the dimension in it never moves. Two consequences:

- **Targeting the locked slot evaluates nothing.** `"optimize_position": "last"` on such a cube has exactly one legal occupant (the dimension already there), so every candidate is skipped and no result is produced. That is the honest answer, not a failure: the run exits normally and logs the skip count. Earlier versions asked per candidate whether *that candidate* had strings, let a numeric one through, and sent TM1 a reorder it then rejected.
- **Every other position works normally,** minus one candidate: the locked dimension is never swept out of its slot, so a locked cube's position sweep has N-2 candidates rather than N-1.

A string-bearing dimension that is *not* in the last storage slot is not locked and is an ordinary candidate.

## CLI

```bash
optimuspy optimize sales_position.json
```

The repository includes [`samples/optimize_position.json`](../examples/optimize_position.json) as a starting point.

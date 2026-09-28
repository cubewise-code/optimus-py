# Dimension Optimization

Test every valid position for one specific dimension while keeping others fixed. It's the mirror of [Position Optimization](position-optimization.md): instead of asking "what dimension should go in this slot?", it asks "where should this dimension go?".

## When to use

- You suspect a specific dimension is in the **wrong slot** and want to find its best home.
- After a greedy run, you want to **double-check** that one specific dimension's position is justified.
- A new dimension was added to the cube and you want to see where it fits best.

## JSON config example

```json
{
  "instance": "tm1srv01",
  "cube": "Sales",
  "executions": 5,
  "output": "csv",
  "optimize_dimension": "Customer"
}
```

`optimize_dimension` must be a **valid dimension name** in the cube. OptimusPy validates this on startup, so typos fail fast with a clear error.

## What it does

OptimusPy keeps every other dimension fixed in its current position and slides the target dimension through every position, measuring at each one.

For an 8-dimension cube that's 7 evaluations, one per position other than the one the dimension is in today (the current position is what the original-order baseline measures, so there's no point testing it again). That's a fraction of a full greedy run, whose length depends on the cube's cardinality profile.

## Interaction with the locked slot

The constraint is on the **slot**, not on the dimension: if the dimension sitting last in the storage order has string elements, that last slot is locked and nothing else can move into it. So on a cube with a locked slot, the sweep skips the last position and tests one fewer (6 positions on an 8-dimension cube). A dimension that carries string elements somewhere else in the order isn't special; it's tried in every open position like any other.

One thing to bear in mind is that if `optimize_dimension` names the locked dimension itself, every move of it is refused, so the run evaluates nothing and the log reports the skipped candidates. See [The Locked Slot](../concepts/string-element-constraint.md).

## CLI

```bash
optimuspy optimize sales_dimension.json
```

The repository includes [`samples/optimize_dimension.json`](../examples/optimize_dimension.json) as a starting point.

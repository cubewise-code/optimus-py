# Dimension Position Rules

Constrain the greedy search by locking specific dimensions to specific positions. The algorithm only permutes the remaining dimensions.

## When to use

- A specific dimension is **always queried first** in your workload, so you lock it to position 0 to avoid testing orders where it isn't.
- A measure dimension that **must** stay at the last position (string elements force this anyway, but the explicit rule is documentation).
- An **internal best-practice** says "Currency always goes last among non-string dims".

## JSON config example

```json
{
  "instance": "tm1srv01",
  "cube": "Sales",
  "executions": 5,
  "output": "csv",
  "dimension_position_rules": [
    { "dimension": "Time",     "position": 0 },
    { "dimension": "Currency", "position": 3 }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `dimension` | string | Dimension name. Must exist in the cube. |
| `position` | integer | 0-based position. Must be valid for the cube's dimension count. `"first"` and `"last"` are accepted as names for the end slots. |

Multiple rules may target different dimensions; they cannot target the same position, and one dimension cannot have two rules.

A `position` must be a JSON number, not a string: write `3`, not `"3"`. Both name the same slot, so OptimusPy says exactly that rather than reporting an unreadable position at a value you can see is a number.

!!! warning "0-based here, 1-based in `optimize_position`"

    `position` counts from **0**: `3` is the fourth slot. The separate [`optimize_position`](../modes/position-optimization.md) field counts from **1**, where `3` is the third slot. Each matches its own long-standing documentation, so neither is a defect, but if you use both fields in one config, convert between them. `"first"` and `"last"` mean the same thing in both.

Positions count against the cube's **storage** order (`get_storage_dimension_order()`), not the presentation order shown in Architect.

## Interaction with greedy search

OptimusPy:

1. Validates the rules against the cube's storage order, right after reading it and before any reorder is sent. A typo, an out-of-range position, a value that names no slot, two rules on one position or one dimension, or a collision with the string-element lock all fail fast. Every bad rule is reported at once, so a config is fixed in one pass.
2. **Pre-applies** the rules: each named dimension is seated at its position, and the remaining dimensions keep their relative storage order in the slots that are left. This pre-applied order (not the cube's current order) is where the search starts.
3. Runs greedy on the remaining N - (number of ruled dims) positions. A ruled dimension is immovable and its slot is never a sweep target, exactly as for the locked dimension and for `dimensions_to_exclude`.
4. Skips and logs any candidate order that would violate a rule. With pre-application in place the search does not generate one, so this is a backstop rather than the mechanism.

The skip messages are logged at DEBUG level, which is off by default, so run with `-v` to see them (see [Optimization Logging](../concepts/how-it-works.md#optimization-logging)). The result count reflects only the orders that were actually evaluated.

## Interaction with `dimensions_to_exclude`

| Field | Effect |
|---|---|
| `dimensions_to_exclude` | Removes the dimension from the swap pool, so it stays in its **current** position. |
| `dimension_position_rules` | Forces the dimension to a **specific** position (which may differ from the current). |

Use `dimensions_to_exclude` when you want to leave a dimension where it is. Use `dimension_position_rules` when you want to enforce a specific layout.

A dimension may not appear in both (one says leave it alone, the other says move it), and naming it twice fails at startup. The two fields can still be used together on *different* dimensions. Note that pre-application can shift an excluded dimension's index, because seating a ruled dimension moves everything after it along; the exclusion means the greedy never moves it, measured from the pre-applied order the search starts on.

## Interaction with the string-element constraint

The [locked slot](../concepts/string-element-constraint.md) is a server constraint, so it wins over a rule, which is a preference. A rule that moves the locked dimension off the last slot (or hands that slot to another dimension) fails on startup:

```
ERROR: Invalid dimension_position_rules for cube 'Sales':
  dimension_position_rules[0]: 'Currency' has string elements and is locked to position 7; this rule places it at 3
```

The check runs after the cube's storage order is read (the lock is a property of the cube, not of the config) but before any reorder is sent, so nothing has been modified when it fires. Run with `-v` if you need the full traceback.

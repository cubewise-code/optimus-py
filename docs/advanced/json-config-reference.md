# JSON Config Reference

Every field accepted by an OptimusPy cube config, with types, defaults, and validation rules.

!!! note "Optimize DB uses a different schema"
    This page covers the per-cube config used by `optimize` and `set`. The `optimize-db` mode takes instance-scoped **instructions** instead, because `cube`, `views`, `executions` and `output` have no meaning for a whole-instance sweep. See [Optimize DB Mode](../modes/optimize-db.md).

## Required fields

| Field | Type | Description |
|---|---|---|
| `instance` | string | Section name from `config.ini`. |
| `cube` | string | Name of the cube to optimize. |
| `executions` | integer | How many times each query/process runs per iteration. Median wins. |
| `output` | string | `"csv"` or `"xlsx"` (case-insensitive). Always also generates `.html`. The value isn't validated: anything other than `xlsx` produces a CSV. |

## Optional fields: common

| Field | Type | Default | Description |
|---|---|---|---|
| `views` | array of strings | `[]` | Public view names to benchmark. Leave it out for a RAM-only optimization. Every view listed must exist, in every mode (including `set`). |
| `processes` | array of strings | `[]` | TI process names to benchmark. Each runs `executions` times. Every process listed must exist. |
| `process_parameters` | object | `{}` | Per-process parameters, keyed by process name. A key that matches no process in `processes` is ignored. See [Multi-Process](multi-view-multi-process.md). |
| `update` / `auto_apply` | boolean | `false` | `true` writes the best order back to the cube. `false` restores the original. The UI writes `auto_apply`; both keys mean the same thing. |
| `fast` | boolean | `false` | Fast fold: seed from a cardinality-ascending order over the movable dimensions, then refine only the τ-undecided dimensions (at most 2 passes). `false` runs the thorough τ-frontier search. |
| `dimensions_to_exclude` | array of strings | `[]` | Keep these dims fixed. Honoured by the greedy search and by position mode; ignored by predefined and dimension modes. |

## Optional fields: mode-specific

Exactly one of these may be set. They're mutually exclusive.

| Field | Type | Used by |
|---|---|---|
| `predefined_orders` | array of arrays of strings | [Predefined mode](../modes/predefined-orders.md) |
| `optimize_position` | string or integer | [Position mode](../modes/position-optimization.md). **1-based**, see the note below. |
| `optimize_dimension` | string | [Dimension mode](../modes/dimension-optimization.md) |

## Optional fields: constraints

| Field | Type | Description |
|---|---|---|
| `orders_to_ignore` | array of arrays of strings | Skip these orders during the greedy search. Ignored in the other modes. |
| `dimension_position_rules` | array of objects | Lock dims to specific positions. **0-based**, see the note below. Honoured by the greedy search; in the other modes the rules are still validated (a typo fails the run) but don't constrain the search. See [Dimension Position Rules](dimension-position-rules.md). |

!!! warning "The two position fields count from different origins"

    `optimize_position` is **1-based**: `3` is the third slot. `dimension_position_rules[].position` is **0-based**: `3` is the fourth slot. Each matches its own documentation and has always behaved that way, so neither is a defect, but they are not the same scale, and a config that uses both needs converting between them. `"first"` and `"last"` are accepted by both and mean the same thing in each.

## Which order a position counts against

Every position (`optimize_position` and `dimension_position_rules[].position` alike) resolves against the cube's **storage** order (`get_storage_dimension_order()`), not the presentation order shown in Architect. The two are identical on most cubes and differ on ones that have already been reordered; the storage order is the one that determines RAM and query behavior, and is the only order OptimusPy's engine reasons about.

## Validation rules

OptimusPy validates the shape of the config on startup, so these errors fail fast before it connects to TM1:

- All required fields must be present.
- `views` must be an array (or absent).
- For `set` mode: `predefined_orders` must have exactly one entry.
- Only one of `predefined_orders` / `optimize_position` / `optimize_dimension` may be set.
- `optimize_position` must be `"first"`, `"last"`, or an integer ≥ 1.
- `optimize_dimension` must be a non-empty string.
- Each entry in `predefined_orders` must be a non-empty array of non-empty strings with no repeated dimension. Each entry in `orders_to_ignore` must be an array.
- Each entry in `dimension_position_rules` must have a `dimension` and a `position` key.
- `process_parameters` must be an object whose values are `{param: value}` objects.

A second set of checks needs the server, so it runs right after connecting and before the first reorder: the cube, every view and every process must exist; every predefined order must be an order of this cube (right length, known names, no duplicates); every position rule must name a real dimension and a position in range; and `optimize_dimension` must be one of the cube's dimensions. Any of these ends the run with the message and exit code 1, with nothing changed on the server.

## Examples for each pattern

Minimal greedy:

```json
{ "instance": "tm1srv01", "cube": "Sales", "executions": 5, "output": "csv" }
```

Greedy + views + auto-apply:

```json
{
  "instance": "tm1srv01",
  "cube": "Sales",
  "views": ["Optimus_View1"],
  "executions": 5,
  "output": "xlsx",
  "update": true
}
```

Predefined, two candidates:

```json
{
  "instance": "tm1srv01",
  "cube": "Sales",
  "executions": 5,
  "output": "csv",
  "predefined_orders": [
    ["Time", "Version", "Product", "Customer", "SalesMeasure"],
    ["Customer", "Product", "Time", "Version", "SalesMeasure"]
  ]
}
```

Set (apply only):

```json
{
  "instance": "tm1srv01_prod",
  "cube": "Sales",
  "executions": 1,
  "output": "csv",
  "predefined_orders": [["Time", "Version", "Product", "Customer", "SalesMeasure"]]
}
```

Position, optimize last:

```json
{
  "instance": "tm1srv01",
  "cube": "Sales",
  "executions": 5,
  "output": "csv",
  "optimize_position": "last"
}
```

Greedy with constraints:

```json
{
  "instance": "tm1srv01",
  "cube": "Sales",
  "executions": 5,
  "output": "csv",
  "dimensions_to_exclude": ["Time"],
  "dimension_position_rules": [
    { "dimension": "Version", "position": 2 }
  ],
  "orders_to_ignore": [
    ["Product", "Customer", "Time", "Version", "SalesMeasure"]
  ]
}
```

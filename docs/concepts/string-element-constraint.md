# The Locked Slot (String Elements)

TM1 stores string values only in the **last dimension of a cube's storage order**. OptimusPy does not work around that; it recognizes when a cube is subject to it and refuses to propose an order the server would reject.

## The rule, stated once

A cube has one authoritative dimension order: `tm1.cubes.get_storage_dimension_order()`.

If the dimension sitting in the **last position of that order** contains string elements, that position is **locked**. The dimension never moves, whatever the order source, and any candidate order that would move it is skipped with a logged reason while the run continues with the next candidate. If the last dimension is numeric-only, there is no lock and every position is free.

OptimusPy never relocates a dimension to satisfy this. It skips the order.

## It locks a *position*, not a *dimension*

This distinction decides the one case where OptimusPy's behavior is not obvious.

Dimensions are shared between cubes. A dimension can carry string elements because of how *another* cube uses it, while in this cube it is an ordinary sparse dimension somewhere in the middle of the order. That dimension is **not** locked here. It is a swap candidate like any other and is placed by [cardinality](cardinality-aware-greedy.md).

Only the dimension in the last storage slot is locked, and only when it has strings.

> **Changed in 2.0.0.** Earlier versions moved *every* string-bearing dimension to the back of the proposed order, on the assumption that a cube has at most one. On a cube with a shared string-bearing dimension that is not the measure, 1.x relocated it and 2.0.0 places it by cardinality. This is the one case where the old and new behavior genuinely differ; the decision is recorded in the repository's ADR 0004.

One thing to bear in mind is that two of OptimusPy's cheaper heuristics still follow the old rule: the **Suggested Order** on the UI's Overview tab and the [Optimize DB](../modes/optimize-db.md) pass both keep a string-bearing dimension last. They're quick guesses that never test anything, so being conservative costs them nothing. The measured greedy is the one that knows better, because it confirms each placement with a real reorder.

## What the server does

If a string-bearing dimension is written to any position but last, `update_storage_dimension_order` fails with:

```
TM1 error: String elements not allowed in this dimension position
```

This is a TM1 limitation, not an OptimusPy choice, and it applies whether the dimension is mostly numeric with a single string element or is entirely string-typed. Because the server enforces it regardless, OptimusPy skipping such an order is a **courtesy, not a policy**: it saves a round-trip and a failed write, and it keeps the result count honest.

## How OptimusPy detects it

Once per cube, before any benchmarking: the element types of the **last dimension of the storage order** are queried via `tm1.elements.get_element_types`. One check, one decision, reused for the whole run. Nothing is queried per candidate order.

On a locked cube you get one INFO line at the start:

```
Last slot locked for cube 'Sales': dimension 'Measures' has string elements and never moves
```

The cached **dimension intelligence** in the UI still surfaces a "has strings" badge on *every* dimension that carries strings, including ones that are not locked here. The badge is a property of the dimension; the lock is a property of this cube's last slot.

## Which modes honor it

All of them. The lock is a server constraint, so unlike user preferences ([position rules](../advanced/dimension-position-rules.md), `dimensions_to_exclude`, `orders_to_ignore`, which bind the greedy search, plus `dimensions_to_exclude` in position mode), it applies to explicitly named orders too:

| Mode | On an order that moves the locked dimension |
|---|---|
| Greedy (Thorough and Fast) | Never generated; skipped as a backstop |
| [Predefined orders](../modes/predefined-orders.md) | That order is skipped, the rest of the list still runs |
| [Position optimization](../modes/position-optimization.md) | That candidate is skipped; targeting the last slot evaluates nothing |
| [Dimension optimization](../modes/dimension-optimization.md) | That candidate is skipped; targeting the locked dimension evaluates nothing |
| [Set mode](../modes/set-mode.md) | Warns, applies nothing, **exits 0** |

## What gets logged

A skipped order does **not** appear in the result count. Per skipped order, at DEBUG:

```
Skipping order — 'Measures' has string elements and is locked to the last position; this order moves it to position 0
```

DEBUG is off by default, so run with `-v` to see these (see [Optimization Logging](how-it-works.md#optimization-logging)). At INFO you get the per-cube total instead:

```
Skipped 12 candidate orders for cube 'Sales' (12 locked_slot)
```

Set mode is the exception: there the skip is the whole outcome of the run, so it's logged at WARNING.

## What if I want to remove the string elements?

The TM1 cookbook has detailed guidance; typically you split the dimension into "measure" and "attribute" pieces. Once strings are removed, OptimusPy's [scan](../modes/scan-mode.md) re-detects the change (after a [cache clear](../ui/settings-page.md)) and the last slot is free like any other.

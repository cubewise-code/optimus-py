# The Locked Slot (String Elements)

TM1 treats the **last dimension of a cube's storage order** specially when string elements are involved, and it guards that slot from both sides. OptimusPy doesn't work around it; it recognizes which orders the server would reject and never proposes them.

## The rule, stated once

A cube has one authoritative dimension order: `tm1.cubes.get_storage_dimension_order()`. TM1 applies two rules to its last position, on v11 and v12 alike:

1. **A string dimension that is last stays last.** If the dimension in the last position contains string elements, that position is **locked**: the dimension never moves.
2. **No other string dimension can move into the last position.** A dimension with string elements can sit anywhere else in the order and move freely there, but a reorder that would put it last is refused, even when the cube's last dimension is numeric and the slot is otherwise free.

Any candidate order that breaks either rule is skipped with a logged reason, and the run continues with the next candidate. A dimension without string elements, including a numeric measure dimension, can go anywhere, last included.

OptimusPy never relocates a dimension to satisfy these rules. It skips the order.

## It locks a *position*, and guards it

Dimensions are shared between cubes. A dimension can carry string elements because of how *another* cube uses it, while in this cube it's an ordinary sparse dimension somewhere in the middle of the order. That dimension is **not** locked here. It's a swap candidate like any other in every position except the last, and is placed by measurement; see [The Greedy Search](greedy-search.md).

So on a cube whose last dimension is numeric, the greedy still searches the last slot with every dimension that may go there, and simply doesn't try the string dimensions in it.

> **Changed in 2.0.0.** Earlier versions moved *every* string-bearing dimension to the back of the proposed order, on the assumption that a cube has at most one. 2.0.0 searches a string-bearing dimension that isn't last like any other dimension; the decision is recorded in the repository's ADR 0004.
>
> **Changed in 2.0.3.** 2.0.0 to 2.0.2 knew only the first rule. On a cube whose last dimension was numeric, the greedy tried string dimensions in the free last slot, TM1 refused the reorder and the run stopped ([#141](https://github.com/cubewise-code/optimus-py/issues/141)). The second rule is now enforced everywhere; see ADR 0006.

The **Suggested Order** on the UI's Overview tab and the [Optimize DB](../modes/optimize-db.md) leaf-count pass follow the same two rules. They sort dimensions by size and want the largest one last, so when a string dimension can't take the last slot, the largest dimension that can takes it instead.

## What the server does

A reorder that moves a string dimension out of the last position, or a different string dimension into it, fails:

```
ReorderDimensions: Last dimension has strings and cannot be repositioned.
```

This is a TM1 limitation, not an OptimusPy choice, and it applies whether the dimension is mostly numeric with a single string element or is entirely string-typed. Because the server enforces it regardless, OptimusPy skipping such an order is a **courtesy, not a policy**: it saves a round-trip and a failed write, and it keeps the result count honest.

## How OptimusPy detects it

Once per cube, before any benchmarking, the element types of **every dimension** of the storage order are read via `tm1.elements.get_element_types`. That gives both answers at once: whether the last dimension is locked, and which dimensions may never be moved into the last slot. One check per dimension, one decision, reused for the whole run. Nothing is queried per candidate order.

At the start you get an INFO line for each rule that applies:

```
Last slot locked for cube 'Sales': dimension 'Measures' has string elements and never moves
Never tried in the last slot for cube 'Revenue': ['Month', 'Version'] (string elements, which TM1 refuses to move into the last position)
```

The UI marks every dimension that carries string elements with a **Str** badge: **red** for the last dimension, which is locked there, and **orange** for any other, which can move anywhere except the last position.

## Which modes honor it

All of them. These are server constraints, so unlike user preferences ([position rules](../advanced/dimension-position-rules.md), `dimensions_to_exclude`, `orders_to_ignore`, which bind the greedy search, plus `dimensions_to_exclude` in position mode), they apply to explicitly named orders too:

| Mode | On an order that breaks either rule |
|---|---|
| Greedy (Thorough and Fast) | Never generated; skipped as a backstop |
| [Predefined orders](../modes/predefined-orders.md) | That order is skipped, the rest of the list still runs |
| [Position optimization](../modes/position-optimization.md) | That candidate is skipped; targeting a locked last slot evaluates nothing |
| [Dimension optimization](../modes/dimension-optimization.md) | That candidate is skipped; targeting the locked dimension evaluates nothing |
| [Set mode](../modes/set-mode.md) | Warns, applies nothing, **exits 0** |

A [position rule](../advanced/dimension-position-rules.md) that would put a string dimension last fails at startup instead, before anything is reordered.

## What gets logged

A skipped order does **not** appear in the result count. Per skipped order, at DEBUG:

```
Skipping order — 'Measures' has string elements and is locked to the last position; this order moves it to position 0
Skipping order — 'Month' has string elements, and TM1 refuses to move a dimension with string elements into the last position
```

DEBUG is off by default, so run with `-v` to see these (see [Optimization Logging](how-it-works.md#optimization-logging)). At INFO you get the per-cube total instead:

```
Skipped 12 candidate orders for cube 'Sales' (12 locked_slot)
```

The greedy doesn't even generate a string dimension as a candidate for the last slot, so on a cube like `Revenue` above those orders aren't counted as skipped; they're simply not part of the search, and the `Iteration N of M` total leaves them out.

Set mode is the exception: there the skip is the whole outcome of the run, so it's logged at WARNING.

## What if I want to remove the string elements?

The TM1 cookbook has detailed guidance; typically you split the dimension into "measure" and "attribute" pieces. Once strings are removed, OptimusPy's [scan](../modes/scan-mode.md) re-detects the change (after a [cache clear](../ui/settings-page.md)) and the dimension is free like any other.

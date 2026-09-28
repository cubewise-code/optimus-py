# What Happens During a Run

What OptimusPy decides while an `optimize` run is going.

## The run, step by step

Every `optimize` run follows the same path, whichever mode picks the orders.

<div class="diagram-frame">
  <iframe src="../diagrams/optimize-run.html" title="Steps of an optimize run" loading="lazy"></iframe>
</div>

[Open the diagram full screen](diagrams/optimize-run.html){ target=_blank }

- **Only one mode per config.** `predefined_orders`, `optimize_position` and `optimize_dimension` can't be combined. With none of them, the run uses Greedy, or Fast mode with `"fast": true`.
- **The locked slot.** If the last dimension of the storage order has string elements, TM1 won't let it move, so OptimusPy never moves it. See [The Locked Slot](../concepts/string-element-constraint.md).
- **Your rules bind Greedy and Fast.** `dimensions_to_exclude`, `orders_to_ignore` and `dimension_position_rules` shape the orders they try. Orders you list yourself (Predefined) are only checked against the locked slot. See [Dimension Position Rules](../advanced/dimension-position-rules.md).

The full pipeline, including how the cache and VMM/VMT are handled, is on [How It Works](../concepts/how-it-works.md).

## How Greedy and Fast mode choose

<div class="diagram-frame">
  <iframe src="../diagrams/greedy-and-fast.html" title="How Greedy and Fast mode choose dimension orders" loading="lazy"></iframe>
</div>

[Open the diagram full screen](diagrams/greedy-and-fast.html){ target=_blank }

Greedy fills slots from the outside in; Fast starts sorted and fixes the close calls. The details are on [Optimize Mode](../modes/optimize-mode.md) and [Cardinality-Aware Greedy](../concepts/cardinality-aware-greedy.md).

**Next:** [Reading the Result →](reading-the-result.md)

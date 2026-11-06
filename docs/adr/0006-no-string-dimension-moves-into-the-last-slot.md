# No dimension with string elements moves into the last slot

Amends [ADR-0004](0004-storage-order-is-the-frame-and-only-the-last-slot-is-locked.md).

## Context

ADR-0004 stated TM1's string constraint as one rule on one position: if the dimension in the last storage slot has string elements, it never moves. A cube whose last dimension is numeric therefore had "no lock, and every position is free", and a string-bearing dimension elsewhere in the order was "searched like any other".

Issue #141 showed that half the rule was missing. The Revenue cube in the 24Retail model has a numeric last dimension (`Revenue`) and two dimensions with string elements in the middle (`Month`, `Version`). The greedy sweeps the last slot first, tried `Month` there on its fourth reorder, and TM1 refused:

```
ReorderDimensions: Last dimension has strings and cannot be repositioned.
```

The error was fatal, so the run ended and the UI suggested resuming, which would have retried the same order.

A probe on a throwaway cube settled the behaviour on both supported versions, tm1srv01 (v11, 11.8) and tm1srv02 (v12, 12.6), with identical results:

| Reorder | v11 | v12 |
|---|---|---|
| A string dimension moved around the middle | accepted | accepted |
| A string dimension moved **into** the last slot (last dimension numeric) | refused | refused |
| A numeric dimension moved into the last slot | accepted | accepted |
| The string dimension already last moved **out** of it | refused | refused |

Both refusals carry the same message. The old documentation's claim that a string dimension "written to any position but last" fails was also wrong: string dimensions sit and move in the middle freely.

## Decision

**TM1's string rule has two sides, and the order frame enforces both.** The locked slot stays as ADR-0004 decided. In addition, a dimension with string elements may never be moved into the last slot; the one string dimension allowed there is the one already in it.

- **One check per cube, before the sweep.** Core reads the element types of every dimension once (`core.string_dimensions`) and builds the frame with that set. `OrderFrame.can_be_last` answers per dimension; `admits` refuses an order that breaks the rule with the code `string_last_slot`, as tier 2 (skipped with a logged reason, processing continues), exactly like the locked slot. ADR-0004's objection to per-candidate server calls stands: the frame decides without the server.
- **The greedy doesn't generate those orders.** At the last slot, string dimensions are left out of the candidates, and the promised total ("Iteration N of M") leaves them out too, so a run still ends on N of N. The frame's refusal stays as the backstop.
- **Every other mode is covered by the frame**, as for the locked slot: predefined orders and position and dimension candidates are skipped; set mode warns and exits 0; a position rule that seats a string dimension last, directly or by freeing the last slot so that one lands there, fails at startup.
- **The heuristics build orders TM1 accepts.** The Suggested Order and the Optimize DB leaf-count target used to move every string dimension to the back, which ADR-0004 called conservative. On a cube like Revenue it is illegal. Both now go through `order_frame.string_safe_order`: sort by leaf count, keep a string dimension last only if it is already last, otherwise give the last slot to the largest dimension without strings. This builds an order rather than repairing a candidate, so it does not conflict with "never relocate".
- **The UI says which side applies.** Every dimension with string elements carries a Str badge: red when it is the cube's last dimension (locked there), orange elsewhere (it moves freely but never into the last slot).

## Considered alternatives

- **Catch the server's refusal and skip the order.** Rejected. It costs a failed reorder per string dimension on every run, it relies on parsing an error message, and the promised total would still count orders that can never be measured. The frame already knows enough to never send them.
- **Treat every string dimension as locked where it is.** Rejected. It isn't what TM1 does: a string dimension moves freely in the middle, and freezing it would take it out of the search for no reason.
- **Ask the server per candidate whether its last dimension has strings.** Rejected for the same reason as in ADR-0004: a round-trip per order, inside the measurement loop, for an answer that doesn't change during the run.

## Consequences

- On a cube with a numeric last dimension and string dimensions elsewhere, the greedy, position, dimension and predefined modes complete instead of failing on the first such order. Live tests (`tests/test_live_string_dimensions.py`) reproduce #141 on both versions: the old code fails with TM1's refusal, the new one completes and never sends a string dimension last.
- The frame needs one element-type read per dimension at the start of a run, instead of one for the last dimension.
- `docs/concepts/string-element-constraint.md` is written around both sides of the rule; `CONTEXT.md` describes tier 2 as the server constraints.
- Optimize DB still skips cubes with more than one string dimension (`multiple_string_dims`), even under `pin_last`. With the full rule known, such a cube does have legal orders; bringing it into scope is its own piece of work.

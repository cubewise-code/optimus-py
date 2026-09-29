# The Order Frame

The order frame is the single authority on which dimension orders OptimusPy is allowed to ask a cube for. Every order source consults it (both greedy folds, `predefined_orders`, position optimization, dimension optimization and set mode), and no code enforces the *server* constraint anywhere else. The one user preference enforced outside it is `dimensions_to_exclude` in position optimization, where the executor simply leaves excluded dimensions out of its candidate list.

It is a pure module (`src/optimuspy/order_frame.py`): no `TM1Service`, no I/O, no logging of its own. It returns a verdict and a reason; the caller decides how to report it. That purity is what makes admissibility fully testable offline.

For the user-facing view of the same behavior, see [The Locked Slot](../concepts/string-element-constraint.md) and [Dimension Position Rules](../advanced/dimension-position-rules.md).

## The storage order is the frame

A cube has two dimension orders, and OptimusPy reasons about exactly one of them:

| | Returned by | What it is |
|---|---|---|
| **Storage order** | `get_storage_dimension_order()` | What the server physically stores the cube in, what `update_storage_dimension_order` writes, and the only order that determines RAM and query behavior. **This is the frame.** |
| **Presentation order** | `get_dimension_names()` | The build order shown in Architect, conventionally ending with the measure dimension for readability. Never used for optimization decisions. |

Every position index in this document, in `dimension_position_rules`, and in the frame's own messages counts against the **storage** order.

## What the frame is built from

Two things, and nothing else is required:

- the cube's storage order;
- one boolean: whether the last slot is locked.

The greedy folds additionally supply the user preferences (`dimensions_to_exclude`, `orders_to_ignore`, `dimension_position_rules`). A caller that supplies only the first two gets the server constraint alone, which is exactly what `predefined_orders` and set mode need.

The frame reads the run's `initial_dimension_order`, not a fresh server call at the construction site. On resume that variable comes from the checkpoint before the executors are built, so it carries the true original order rather than a crash-reordered one; see [Checkpoint Format and Recovery](checkpoint-resume.md).

## The three tiers

Admissibility is not one verdict. It is three, and callers handle them differently. The distinction that matters is *"you didn't ask for a coherent thing"* versus *"you asked for something TM1 won't allow"*.

| Tier | What it is | Binds | On refusal |
|---|---|---|---|
| **1, well-formedness** | The candidate is not an order at all: wrong length, unknown dimension name, a duplicate. Almost always a typo. | Every order source | **Fails loudly.** There is nothing coherent to be courteous about, and a silent no-op is the worst available outcome. |
| **2, the server constraint** | The locked slot. | Every order source | **Skipped with a logged reason**, processing continues. The user asked for something legitimate that TM1 will refuse anyway. In the iterating modes the reason is logged at DEBUG, like tier 3; in set mode, where the skip is the whole outcome, it is logged at WARNING. |
| **3, user preference** | Position rules, excluded dimensions, ignored orders. | The greedy folds (and `dimensions_to_exclude` in position optimization) | **Skipped, logged at DEBUG only.** |

Tier 2 is checked before tier 3, so a refusal always names the strongest reason. Each refusal carries a greppable code (`not_a_permutation`, `locked_slot`, `ignored_order`, `position_rule`) alongside the human-readable sentence.

## The locked slot

**If the dimension occupying the last position of the storage order contains string elements, that position is locked.** The dimension never moves, whatever the order source. Any candidate order that would move it is skipped with a logged reason, and processing continues.

Four consequences follow, and all four are load-bearing:

1. **Nothing is ever relocated or repaired.** OptimusPy never moves a dimension to satisfy this constraint. A repaired order is one the user did not ask for, reported as though they had; skipping keeps the result set honest, and the result count reflects only orders that were genuinely measured.
2. **It keys off the position, not the dimension.** Dimensions are shared between cubes, and a dimension carries string elements as a property of the whole model. A dimension that has strings because of how *another* cube uses it is an ordinary sparse dimension here, and is placed by cardinality like any other.
3. **A cube whose storage-last dimension is numeric-only has no lock at all**, and every position is free.
4. **It is one check per cube**, taken before the sweep begins, not a server round-trip per candidate.

### Where it produces no results

On a locked cube, `optimize_position: "last"` and `optimize_dimension: <the locked dimension>` evaluate nothing. Every candidate would move the locked dimension, so every candidate is skipped; the run logs the skip count and exits normally with no results. That is the honest answer for a slot with exactly one legal occupant.

### Where the heuristics disagree

Two call sites still apply the older dimension-keyed rule and move every string-bearing dimension to the back: the cardinality suggestion (`_compute_suggested_order`) and the [Optimize DB](optimize-db.md) heuristic pass. On a cube with a shared string-bearing dimension that is not its measure, the measured greedy result and those unmeasured suggestions will recommend different orders. Both are heuristics that propose an order without measuring it.

## Dimension pinning

Three different things hold a dimension in place. The frame distinguishes them because the reasons differ; the search only needs the fact.

| Held by | Set via | Tier | Where it sits |
|---|---|---|---|
| The lock | Nothing, it is the server's rule | 2 | The last slot |
| An exclusion | `dimensions_to_exclude` | 3 | Its original index |
| A position rule | `dimension_position_rules` | 3 | The slot the rule names |

Everything else is movable, and only movable dimensions are swept. The slots held by the three above are **reserved**: never a sweep target.

Cardinality pinning is a separate idea and lives in the greedy, not the frame: a dimension whose leaf count is ≥ τ× every other's has only one candidate slot left and is placed without being tested. That is the degenerate case of the [leaf-count tolerance](../concepts/cardinality-aware-greedy.md), not a rule about admissibility.

## Pre-application

When position rules are set, the search does not start from the cube's current order. The frame produces a **pre-applied order**: each ruled dimension is seated at the slot its rule names, and the remaining dimensions keep their relative storage-order sequence in the slots that are left. The greedy searches from there, over the positions that are not reserved.

Pre-application is the mechanism; `admits()` still checks rules on every candidate, but with the pinned slots reserved the search should never generate a violating order. That check stays as the statement that it does not.

## Guarantees

- One module decides admissibility. `grep -rn "_has_string_elements\|_string_last_skip" src/` returns nothing.
- No TM1 round-trip happens inside a sweep to decide whether an order is allowed.
- A candidate is refused with a reason, never dropped without one: tier 1 raises; tier 2 logs at DEBUG in the iterating modes and at WARNING in set mode; tier 3 logs at DEBUG.
- A refusal never changes the order. There is no repair path.
- The reported result count equals the number of orders actually measured.

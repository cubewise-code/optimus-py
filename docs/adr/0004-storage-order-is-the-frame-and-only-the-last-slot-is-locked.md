# The storage order is the frame, and the last slot is the only thing locked in it

## Context

A TM1 cube has two dimension orders. `get_dimension_names()` returns the **presentation** order — the build order, shown in Architect, conventionally ending with the measure dimension for readability. `get_storage_dimension_order()` returns the **storage** order — what the server physically stores the cube in, what `update_storage_dimension_order` writes, and the only one that determines RAM and query behaviour. Only one of them can be the frame of reference for an optimizer, and reasoning about a cube in the presentation order while the server enforces against the storage order produces a mismatch that is invisible in the results: the engine permutes one list and the server answers about another.

TM1 also imposes one hard constraint on the storage order. It is a constraint on a **position**, not on a dimension: the dimension occupying the last storage position may not be moved out of it if that dimension contains string elements. Stating the rule the other way round — "a dimension with string elements goes last" — sounds equivalent and is not, because dimensions are shared between cubes and a dimension carries string elements as a property of the whole model.

The three tiers of admissibility — well-formedness, the server constraint, user preference — are defined in `CONTEXT.md` under "Order admissibility", which is where the project's vocabulary lives. They are not restated here.

## Decision

**The storage order is the frame.** The engine reasons about `get_storage_dimension_order()` and nothing else. A single pure module, `src/optimuspy/order_frame.py`, is built from that order plus one boolean — whether the last slot is locked — and answers whether a candidate order is admissible, returning a reason when it is not. Every order source consults it: both greedy folds, predefined orders, position and dimension optimization, and set mode. It holds no `TM1Service`, performs no I/O, and logs nothing; the caller logs the reason it returns.

**Only the last slot is locked, and only when the dimension in it has string elements.** That dimension never moves, whatever the order source. Any candidate that would move it is skipped with a logged reason and processing continues. There is no relocation and no repair: OptimusPy never moves a dimension to satisfy this constraint. A cube whose storage-last dimension is numeric-only has no lock, and every position is free.

**The lock is one check per cube, taken before the sweep.** Asking the server whether a *candidate* dimension carries strings, inside the measurement loop, is both a round-trip per candidate and the wrong question: what matters is whether the resulting order is admissible, which the frame decides without the server.

**The frame reads the run's `initial_dimension_order`, not a fresh `get_storage_dimension_order()` call at the construction site.** On resume that variable is reassigned from the checkpoint ([ADR-0003](0003-resume-validates-dimension-set-and-recovers-in-flight-reorder.md) §2) *before* the executors are built, so it carries the true original order. The locked dimension is the same either way — TM1 never permitted a reorder that moved a string dimension off the last slot — but a fresh read would re-derive the RAM baseline from a crash-reordered cube, which is silent and visible only in the final figures.

**Both greedy folds derive the front/back split from the full storage order.** `mid = tau.midpoint(len(dimensions))` (`executors.py:448`, `:571`), so setting `dimensions_to_exclude` no longer shifts which metric ranks a position. The claim is precise: the *set of positions swept* still varies with exclusions, because an excluded dimension's slot is still skipped. What no longer varies is the **range and the break point**, and therefore the τ ranking each position receives — which is the behaviour [ADR-0002](0002-cardinality-pruning-keyed-to-optimization-metric.md) specifies. ADR-0002 is referenced by this decision, not revised by it.

## Considered alternatives

- **Make the lock a property of the dimension rather than the position.** Rejected, and this is the substantive one. A dimension shared with another cube can carry string elements because of how *that* cube uses it, while here it is an ordinary sparse dimension in the middle. A dimension-keyed rule moves it to the back on every cube in the model; the position-keyed rule leaves it where cardinality puts it. The two rules recommend genuinely different orders on such a cube.
- **Amend ADR-0002 and ADR-0003 in place.** Rejected: both are accurate records of decisions taken under the arrangement this work replaces. A fourth ADR is cheaper than editing two, and rewriting a decided record to match later code destroys the reason the record exists.
- **Keep a relocation step as defence in depth.** Rejected. Once the engine reads the storage order, `resulting_order[-1]` *is* the storage-last dimension, which *is* the one the lock keys off, so a relocation branch can no longer fire. Code that cannot fire is not defence — it is a second rule waiting to disagree with the first, which is how one constraint came to have three implementations.
- **Have the frame repair an inadmissible order instead of skipping it.** Rejected: a repaired order is one the user did not ask for, reported as though they had. Skipping with a logged reason keeps the result set honest, and the result count reflects only orders that were genuinely measured.
- **Apply the frame's user preferences to explicitly named orders too.** Rejected. The lock is a server constraint and binds everything; position rules, excluded dimensions and ignored orders are preferences that shape a *search*. A TM1 developer who names an exact order in `predefined_orders` or `set` mode gets it.

## Consequences

- One module decides admissibility. No other code enforces the string constraint: `grep -rn "_has_string_elements\|_string_last_skip" src/` returns nothing.
- Production TM1 round-trips are removed from inside the sweep.
- **On a locked cube, `optimize_position: "last"` and `optimize_dimension: <the locked dimension>` evaluate nothing.** Every candidate would move the locked dimension, so every candidate is skipped; the run produces no results, logs the skip count, and exits normally. That is the honest answer for a slot with exactly one legal occupant, and it will look like a regression to anyone who was running those two configurations against such a cube.
- **The greedy and the heuristics can recommend different orders.** `_compute_suggested_order` (`core.py:760`, `suggested = non_string_dims + string_dims`) and the `optimize-db` heuristic pass's target builder (`optimize_db.py:202`, `target = numeric + string_dims`) both still move every string-bearing dimension to the back. On a cube with a shared string-bearing dimension that is not its measure, the measured greedy result and the unmeasured suggestion will disagree. Both are heuristics that propose an order without measuring it; bringing them onto the frame is its own piece of work.
- `dimensions_to_exclude` no longer changes which metric ranks a position.
- Because the frame is pure, admissibility is fully testable offline. That is what lets the test suite split into an offline default and an opt-in live suite without a `FakeTM1`.
- `docs/concepts/string-element-constraint.md` is written around the locked slot; `CONTEXT.md` carries **order frame**, **locked slot** and **the three tiers** as project vocabulary.

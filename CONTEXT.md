# OptimusPy

OptimusPy benchmarks TM1 cube dimension-storage orders to find the order that minimises RAM (and/or query time). It reorders a cube's storage dimensions, measures the resulting per-cube memory, and reports the best permutation.

## Language

### Memory measurement

**RAM baseline**:
The per-cube memory figure OptimusPy reads once at the start of a run (and once more on resume, to re-anchor); every other permutation's RAM is derived from the `%` the reorder returns. Always held internally in **bytes**.
_Avoid_: "memory footprint", "size"

**cube_memory_used**:
The canonical MetricService metric name for a cube's total memory. Replaces the v11-only `StatsByCube` → `Total Memory Used` lookup. Version-agnostic in *name*, but its `Unit` differs by server version.
_Avoid_: "Total Memory Used" (that is the v11 MDX measure, now an implementation detail behind the metric)

**MetricService**:
The version-agnostic TM1py service (`tm1.metrics`, TM1py ≥ 2.3.0) that serves model statistics. `by_cube()` returns per-cube gauge rows; OptimusPy uses it as the single source of RAM data on both v11 and v12.
_Avoid_: "StatsByCube" / "PerfCubes" (v11 control cubes, now hidden behind MetricService)

**Unit (of a metric)**:
The unit tag MetricService attaches to each metric value (`B`, `KB`, `MB`, `#`, `%`…). MetricService normalises metric *names* across versions but **not** units — `cube_memory_used` is `B` on v11 and `KB` on v12. Callers must read `Unit` and convert to bytes.
_Avoid_: assuming a fixed unit; hardcoding `×1024`

### Dimension shape

**cardinality**:
The number of leaf-level elements in a dimension. The cheap, reorder-free signal OptimusPy uses to decide, pin, and prune dimension orderings in the greedy optimizer. Distinct from RAM: a high-**cardinality** dimension is not necessarily a large **RAM baseline** contributor (density/sparsity matters more), which is why placement is still confirmed by measurement.
_Avoid_: "size" (reserved-against for memory — ambiguous), "dimension size", "number of elements" (imprecise about leaf vs consolidated)

**leaf-count tolerance (τ)**:
The ratio that decides whether the greedy will test *both* relative orderings of two dimensions. If one dimension's **cardinality** is ≥ τ× another's, theory decides the order (larger ⇒ sparser ⇒ later) and the reverse ordering is never tested; within τ the pair is *undecided* and both orderings are tested, because density — which OptimusPy cannot know in advance — may justify either. Larger τ ⇒ looser ⇒ more orderings tested. Applied full-strength at RAM-ranked positions, looser at query-ranked positions, and not at all at process-ranked positions (see `docs/adr/0002`). Pinning a dimension (e.g. a 50k-leaf dim to the back) is just the degenerate case where τ leaves it the only candidate for an end position.
_Avoid_: "bucket" / "size band" — an earlier, lossier framing; dimensions do not fall into fixed cardinality bands, ordering is decided pairwise.

### Order admissibility

**order frame**:
The single authority on a cube's dimension order (`src/optimuspy/order_frame.py`). It is built from the cube's storage order — `get_storage_dimension_order()`, never the presentation order — plus whether the last slot is locked, and it answers one question: is this candidate order admissible, and if not, why. Every order source consults it: both greedy folds, predefined orders, position and dimension optimization, and set mode. Pure: no `TM1Service`, no I/O, no logging — the caller logs the reason it returns. Offline-testable in the same category as the **leaf-count tolerance (τ)** helpers.
_Avoid_: "validator" (it decides admissibility, it does not repair or relocate anything), "dimension order" unqualified when the *storage* order is meant

**the three tiers**:
Admissibility is not one verdict but three, and callers handle them differently. **Tier 1, well-formedness** — the candidate is not an order at all (wrong length, unknown dimension, duplicate), almost always a typo. It binds every order source and **fails loudly**, because there is nothing coherent to be courteous about and a silent no-op is the worst available outcome. **Tier 2, the server constraint** — the **locked slot**. It binds every order source, and the order is skipped with a logged reason while processing continues: the user asked for something legitimate that TM1 will refuse anyway. **Tier 3, user preference** — position rules, excluded dimensions, ignored orders. Supplied by the greedy folds alone, skipped silently at DEBUG. The tier 1 / tier 2 distinction is the one to hold on to: *"you didn't ask for a coherent thing"* versus *"you asked for something TM1 won't allow"*.
_Avoid_: treating a typo as a constraint collision — that is what lets a misspelled dimension name silently do nothing

**locked slot**:
The last position of a cube's storage order, when the dimension sitting there contains string elements. That dimension never moves, whatever the order source, and any candidate order that would move it is skipped with a logged reason while processing continues. This is a *server* constraint — TM1 rejects the write regardless — which is why it applies to explicitly-named orders too, unlike the user preferences (position rules, excluded dimensions, ignored orders) that only the greedy folds honour. A cube whose storage-last dimension is numeric-only has no lock and every position is free. Note this keys off the *position*, not the dimension: a dimension is shared between cubes, so one carrying string elements somewhere else in the order is not locked and is placed by **cardinality** like any other.
_Avoid_: "string dimension constraint" (implies the dimension is what is locked, rather than the slot), "freeze" / "relocate" (OptimusPy never moves a dimension to satisfy this — it skips the order)

### Instance-wide pass

**heuristic pass** (UI: "Optimize DB", CLI: `optimize-db`):
A single application of the cardinality heuristic to every cube in an instance, one cube at a time, under a wall-clock budget. Nothing is benchmarked: no permutation is tested and no query is timed. Its purpose is to get the whole model close to a good order cheaply, so that the *measured* search — `optimize` mode — can afterwards run against a smaller **RAM baseline**. Smallest-to-largest is not optimal, but it lands close on most cubes.
_Avoid_: calling it "optimization" without qualification — that word is reserved for the measured greedy search, which carries evidence a heuristic pass does not.

**plan**:
The read-only output of `--dry-run`: the ordered cube queue, each cube's target order, every skip reason, the coverage figure, and the chores that were active when it was built. Contains no server writes and is the artifact an operator reviews before committing a weekend to the sweep.

**run artifact**:
The execution state written after every cube: per-cube status, original order (so a regression can be reverted), pre-reorder **RAM baseline**, the reported `%`, and the chore lifecycle state. It is the resume point, the final report, and — when the process dies with chores deactivated — the only record of which chores must be re-activated.

**budget**:
The wall-clock limit, checked *only between cubes*. A running `ReorderDimensions` is a blocking server-side rebuild with no safe abort, so a sweep overshoots by the duration of whatever cube it last started. The budget exists to stop the sweep running forever, not to guarantee an end time. The next cube's duration is extrapolated from observed throughput (median bytes/second over the last few cubes); no ETA is ever produced.

**derived saving**:
A per-cube `%` computed from absolute **cube_memory_used** reads instead of taken from `update_storage_dimension_order`'s return value. Only happens when a dropped connection loses the response: the reorder is atomic so the cube is at either the original or the target order, but the `%` is gone and is nowhere on the server. Tagged `derived` in the **run artifact** because it is a measurement, not the server's own arithmetic.

## Relationships

- A **permutation** (storage dimension order) produces one **RAM baseline** reading via **cube_memory_used**
- **cube_memory_used** is served by **MetricService**, carrying a **Unit** that must be converted to bytes at the read boundary
- Every candidate **permutation** is admitted or refused by the **order frame** before it reaches the server; the **locked slot** is the one rule binding on every order source, while **cardinality** and **leaf-count tolerance (τ)** shape only what the greedy folds propose

## Scope of the v12 migration

Behavior is **frozen** — only the *data source* changes. The RAM model is unchanged: read a **RAM baseline** once at the start, then derive every other permutation's RAM by applying the `%` change that `update_storage_dimension_order` returns (confirmed to return a real `%` on v11 **and** v12). OptimusPy does **not** read per-permutation memory from the server. The migration swaps the `}StatsByCube` MDX reads for `MetricService.by_cube()` reads. On v11 the Performance Monitor must still be active before reading (toggled via `tm1.metrics` lifecycle methods); on v12 nothing is toggled because the metric is always available. The VMM/VMT cap raise-and-restore is v11-only too — it reads/writes the `}CubeProperties` control cube, which does not exist on v12, so optimize mode simply skips it there.

## config.ini location resolution

Both entry points (`optimuspy` CLI and `python -m optimuspy.ui`) resolve the connection config the same way, via `resolve_config_path`:

- `--config PATH` (explicit) beats the built-in default.
- No `--config` ⇒ falls back to `config/config.ini`, which stays **writable** (the UI Settings page can create/edit/delete instances in it).
- Explicit `--config PATH` ⇒ treated as owned by another tool and **read-only**; OptimusPy never writes to it. This is what lets a `config.ini` be shared safely with other tm1py tools (e.g. RushTI) instead of duplicating credentials.
- Explicit `--config PATH` that doesn't exist ⇒ fail-fast: print `ERROR: config.ini not found: <path>` and exit 1, no traceback. (The default path has no such existence check; it's left to the existing read path.)

Out of scope / not shipped: no environment-variable override, no keyring integration (deferred to a later phase), no comment-preserving INI writer.

## Flagged ambiguities

- "RAM" / "memory" was used loosely — resolved: OptimusPy's internal canonical unit is **bytes**; conversion from the metric's reported **Unit** happens once, at the read boundary, so all downstream `/ 1024**3` GB math is unchanged.

## Example dialogue

> **Dev:** "After a permutation, where do we get the new **RAM baseline**?"
> **Domain expert:** "From **MetricService** `by_cube()` — read the `cube_memory_used` row, then convert by its **Unit**: `B`→×1, `KB`→×1024. Never assume bytes; v12 reports KB."

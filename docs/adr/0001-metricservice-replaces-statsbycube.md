# MetricService replaces the }StatsByCube cube as OptimusPy's RAM source

## Context

OptimusPy reads per-cube memory to choose the best dimension-storage order. It did this by querying the `}StatsByCube` control cube via MDX (`Total Memory Used`), which only exists on TM1 v11 — the cube was deprecated in v12, so OptimusPy could not run there at all.

## Decision

Read RAM from the version-agnostic TM1py `MetricService` (`tm1.metrics.by_cube()`, TM1py ≥ 2.3.0), using the `cube_memory_used` metric, on both v11 and v12.

Three things make this non-obvious and are deliberate:

1. **Convert via the `Unit` column — never assume a fixed unit.** MetricService normalizes metric *names* across versions but **not** their units: `cube_memory_used` is reported in `B` on v11 and `KB` on v12 (and sibling memory metrics differ again). OptimusPy converts whatever `by_cube()` returns into **bytes** at the read boundary (`B→×1`, `KB→×1024`, `MB→×1024²`; unknown unit fails loud), so all downstream `/1024**3` GB math is untouched. Hardcoding `×1024` would silently break on a unit change — do not "simplify" the `Unit` branch away.

2. **Behavior is otherwise frozen.** The RAM model is unchanged: read the baseline once, then derive every other permutation from the `%` that `update_storage_dimension_order` returns (confirmed to return a real `%` on v11 and v12). OptimusPy does not read per-permutation memory from the server.

3. **Lifecycle and errors are version-gated.** The major version is detected once (`get_product_version()`). On v11 the Performance Monitor must still be active before reading (toggled via `tm1.metrics` lifecycle methods, prior state restored); on v12 nothing is toggled because the metric is always available. The "Performance Monitor must be activated" error and the read-retry/wait loop remain v11-only. The VMM/VMT cap raise-and-restore (read/written via the `}CubeProperties` control cube) is also v11-only — `}CubeProperties` does not exist on v12, so optimize mode skips it there rather than crashing.

4. **The baseline read is validated before it is trusted.** `cube_memory_used` reports a skeleton for a cube whose data is not yet resident — tens of KB for a cube that will settle at tens of MB — and that is a property of residency, not of a version. The v12 read polls until the value *plateaus* (a re-read no longer materially larger than the largest seen), which is sound against a reading still rising but cannot tell a settled cube from an unmaterialised one: two equal reads are the same observation either way. The `%` chain does **not** route around it, because the two failures are one cause and not two — a cube that is not resident costs the same in every order, so a skeletal baseline and 0% from every reorder arrive together. The reading is therefore cross-checked against `cube_num_populated_numeric_cells` and `cube_num_populated_string_cells` from the same `by_cube()` payload, which report correctly while `cube_memory_used` does not, and a density below one byte per populated cell is refused outright rather than optimized against. v11's read path is unchanged (frozen).

## Considered alternatives

- **Hardcode `×1024` for v12.** Rejected: wrong for sibling memory metrics already in bytes, and brittle if the server's reported unit ever changes. Reading the `Unit` column is the contract the service is designed around.
- **Read `cube_memory_used` per permutation instead of applying the `%`.** Rejected: unnecessary server round-trips and reintroduces sampling-freshness risk, for no benefit over the existing baseline-plus-`%` model.

## Consequences

- OptimusPy now serves TM1 v11 and v12 (PAoC/PAaaS) from a single code path.
- The unit conversion itself is guarded offline (`tests/test_metrics.py`), so CI catches a regression in it. What only a live run can establish — that a v11 and a v12 run of the same cube reach the same winner — is guarded by the two-instance parity gate (`samples/validate_v11_v12_parity.py`, driven by `tests/test_live_parity.py`), which is opt-in and deliberately outside CI.

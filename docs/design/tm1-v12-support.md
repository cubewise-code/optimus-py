# TM1 v11 and v12

OptimusPy serves TM1 v11 and TM1 v12 (Planning Analytics on Cloud / as a Service) from a single code path. This document states what differs between the two versions and what does not.

The v11-only `}StatsByCube` control cube was the original RAM source and does not exist on v12. Reading memory through TM1py's version-agnostic `MetricService` is what makes one code path possible. The decision is recorded in the repository's ADR 0001.

## MetricService

`tm1.metrics.by_cube()` (TM1py ≥ 2.3.0) returns per-cube metric rows on both versions. OptimusPy reads `cube_memory_used` from it as its single source of RAM data, and uses the same call for scan mode's whole-instance sweep; the service already excludes `}`-control cubes and the synthetic total row.

The major version is detected **once per connection** (`get_product_version()`) and the resulting boolean is threaded down. It gates three things and nothing else: the Performance Monitor lifecycle, the read-retry behavior, and the VMM/VMT handling.

## The Unit conversion

**MetricService normalizes metric *names* across versions but not their *units*.**

`cube_memory_used` is reported in `B` on v11 and in `KB` on v12. Every value is converted to bytes at the read boundary, using the `Unit` the server reports on the row:

| Unit | Multiplier |
|---|---|
| `B` | ×1 |
| `KB` | ×1024 |
| `MB` | ×1024² |

An unknown unit **fails loudly**. The raw number is never passed through, because a silent unit change would corrupt every RAM comparison OptimusPy makes, by a factor of 1024, without any symptom other than wrong answers.

Do not replace the `Unit` branch with a hardcoded ×1024. Sibling memory metrics are already reported in bytes, and reading `Unit` is the contract the service is designed around. The conversion is guarded by offline tests, so a regression in it is caught in CI.

## What differs between v11 and v12

| | v11 | v12 |
|---|---|---|
| `cube_memory_used` unit | `B` | `KB` |
| Performance Monitor | Must be **active** before reading. OptimusPy captures the prior state, activates it if it was off, and restores the prior state on exit. | Nothing is toggled: the metric is always available, and the lifecycle methods raise if called. |
| Read on an empty metric | Retried: the monitor samples on an interval, so the metric can be empty for a short window right after activation. | Not applicable. |
| Baseline read | Retry-on-empty. | Polled until the value plateaus. |
| VMM/VMT cap | Raised for the run and restored afterwards, through the `}CubeProperties` control cube. | `}CubeProperties` does not exist. Optimize mode skips the step rather than failing. See [VMM/VMT Handling](../concepts/vmm-vmt-handling.md). |
| Gauge freshness after a reorder | The Performance Monitor is sampled, so `cube_memory_used` read immediately after a reorder returns the **previous** order's figure. | Tracks a reorder within about a second. |

That last row is the one to hold on to when writing anything that compares two orders: **compare through the percentage channel, not through the gauge.** On v11 the gauge is one sample behind its own reported percentages, so reading it straight after a reorder answers about the order before.

## What does not differ

**The RAM model is unchanged, and it is the same model on both versions.** Read an absolute baseline once at the start, then derive every other permutation's RAM by applying the percentage that `update_storage_dimension_order` returns. `update_storage_dimension_order` returns a real percentage on v11 and on v12. OptimusPy does not read per-permutation memory from the server on either version.

Everything downstream of the read boundary is therefore version-agnostic: the greedy, the order frame, checkpointing, the reports. Only the data source changes.

**Both versions have a full order-dependent RAM signal, and they agree on the winner.** A six-mode parity run over the same cube and data on a v11 and a v12 instance reaches identical winners in every mode.

**Not every rearrangement costs memory, on either version.** Adjacent swaps of similarly-sized dimensions are routinely free, and a 0% for one rearrangement is a true answer rather than a missing one. Only *every* candidate returning 0% means a run learned nothing.

## Residency, not version

A cube whose data is not resident costs the same in every order. So a skeletal `cube_memory_used` reading and 0% from every reorder are both truthful, and they are **one cause seen twice, not two independent faults**, which means the percentage chain cannot be relied on to route around a skeletal baseline. This is a property of residency and not of a server version.

Two defenses, both version-agnostic:

- **The baseline is cross-checked against populated-cell counts.** `cube_num_populated_numeric_cells` and `cube_num_populated_string_cells` arrive in the same `by_cube()` payload and report correctly while `cube_memory_used` is still skeletal, so no extra call is needed. A reading below one byte per populated cell is refused outright with an explanation, rather than optimized against. The floor is set far below any plausible real density (a small numeric cube measures in the low hundreds of bytes per cell), so it catches readings that are impossible, not readings that are surprising.
- **An all-zero run is reported as unmeasurable.** When every order comes back 0.00%, the run says so before announcing a winner, and states that the RAM column and the recommended order are unsupported. It reports this as a fact about that cube on that run, not about the server or its version.

## Validation

Version equivalence is established by a live two-instance parity gate (`samples/validate_v11_v12_parity.py`, driven by `tests/test_live_parity.py`): the same fixture cube and data are built on a v11 and a v12 instance, all six modes are run on each, and the winners are compared.

The gate begins by proving the RAM channel answers at all. It applies one rearrangement known to cost about 12.5% on both engines and requires a non-zero return, retrying before it fails. That tests the exact channel every downstream measurement depends on, rather than waiting on a clock. Nothing after it is trustworthy until it passes.

Where the two versions' searches settle on different winners, the gate measures the step from one winner to the other on both servers rather than inferring it. The searches are hill-climbs and do not generally evaluate each other's winners, so there is often no stored measurement to compare, and two orders that measure the same are a genuine tie, not a disagreement.

The gate is opt-in and deliberately outside CI: it needs two live servers.

## Guarantees

- One code path serves both versions; no version branch exists outside the read boundary and the three gated behaviors.
- Every RAM figure is in bytes by the time it leaves the read boundary.
- An unrecognized unit stops the run instead of producing a wrong number.
- A baseline that cannot be real is refused, not optimized against.
- A run with no RAM signal says so before it reports a winner.

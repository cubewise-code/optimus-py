# VMM / VMT Handling

The main goal of a benchmark is that every timing reflects the real cost of the dimension order, not a cached answer. To make sure of that, on TM1 v11 OptimusPy temporarily sets VMM and VMT to 1,000,000 while it benchmarks a cube, then puts the original values back when it's done. This page explains what these two settings do, why OptimusPy changes them, and what to bear in mind.

On v12 (PAoC/PAaaS) these settings don't exist, so OptimusPy doesn't touch them there.

## What VMM and VMT do

On v11, every cube has two stargate-cache thresholds, stored in the `}CubeProperties` control cube:

| Property | Meaning |
|---|---|
| **VMM** | Maximum memory (in KB) a stargate view is allowed to use. Larger views are not cached. |
| **VMT** | Time threshold (in seconds) a query must take before its result becomes a candidate for caching. |

In normal operation these limits are a good thing, because they let TM1 reuse the result of an expensive query across users instead of calculating it again.

## Why OptimusPy overrides them

The problem is that the same caching gets in the way of a benchmark. If stargate caching is active, query times reflect **cache hits** rather than the real cost of the dimension order: the first execution might take 2 seconds, and every run after that comes back in milliseconds because it hits the cache. Every order would look fast after its first execution, so the comparison would tell you nothing.

Setting VMM and VMT to **1,000,000** (effectively infinity for both) means no result qualifies for caching. Every query runs from scratch, so the timing reflects the true cost of the current dimension order.

## How OptimusPy applies the override

```python
try:
    # v11 only: read the current values, then override them
    original_vmm, original_vmt = retrieve_vmm_vmt(tm1, cube_name)
    write_vmm_vmt(tm1, cube_name, "1000000", "1000000")

    # ... run all benchmark iterations ...
finally:
    # Always restore, even on an error or a cancellation
    if original_vmm is not None:
        write_vmm_vmt(tm1, cube_name, original_vmm, original_vmt)
```

The `finally` block is what makes this safe: the original values go back whether the run finishes, fails, is stopped from the UI, or is interrupted with `Ctrl+C`. A config that's rejected before the override is applied (e.g., a typo in `dimension_position_rules`) never changes the values in the first place, so there's nothing to restore.

One thing to bear in mind is that this can't cover a process that's **forcibly killed** (`kill -9`, a power cut, a blue screen), because nothing gets the chance to run. In that case VMM/VMT may be left at 1,000,000. OptimusPy doesn't record the original values anywhere else, so a new run won't put them back for you. If a run ended that way, we'd recommend checking the cube's VMM and VMT in `}CubeProperties` and setting them back by hand.

## Side effect: cache invalidation

Setting VMM/VMT also invalidates any existing stargate views for the cube. After a benchmark run, the first few user queries rebuild the cache. This is normal and expected; the alternative would be measurements you can't trust.

If the cube is **production-critical** and even a brief warm-up window is a problem, the best approach would be to run OptimusPy on a non-PROD copy (which we'd recommend anyway, see the [PROD Promotion Workflow](../examples/prod-promotion-workflow.md)).

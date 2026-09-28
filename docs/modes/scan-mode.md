# Scan Mode

Discover candidate cubes in an instance, ranked by RAM consumption. Use this as a triage step before deciding which cubes are worth optimizing.

## When to use

- You're starting fresh on a model and don't know which cubes matter most.
- You want to **batch-generate** per-cube JSON configs for the cubes worth benchmarking.
- You need a quick **inventory** of which cubes have a custom dimension order vs the default.

## CLI

```bash
optimuspy scan --instance tm1srv01
```

`--instance` is required and must match a section in `config/config.ini`.

## Output format

A console table sorted by RAM, descending:

```
Cubes accounting for up to 60% of total model RAM (12.43 GB), not yet optimized:

   #  Cube Name           Dims  RAM (GB)  % of Total  Dimension Order
   ─  ─────────────       ────  ────────  ──────────  ────────────────
   1  Sales                  8      4.21       33.9%  ['Time', 'Version', ...]
   2  Budget                 6      2.84       22.8%  ['Year', 'Department', ...]
   3  Forecast               7      0.95        7.6%  ['Time', 'Scenario', ...]

  Total: 3 cubes, 8.00 GB (64.4% of model RAM)
```

By default, **already-optimized cubes** (where the visible dimension order differs from storage order) are excluded. To see them, use the UI's Optimize page with **Include optimized** ticked.

## Generating config files

Add `--output` with a directory to write one JSON config per candidate, ready to feed back into `optimuspy optimize`:

```bash
optimuspy scan --instance tm1srv01 --output configs/auto/
```

Each generated file uses safe defaults (`executions: 5`, `output: csv`, no views/processes). Edit each one to add views, processes, or position rules before running.

## Use from the UI

The Optimize page runs the same scan automatically when you connect to an instance. The CLI mode is mostly for scripting — e.g. nightly inventory of cubes that need attention.

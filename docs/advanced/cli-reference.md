# CLI Reference

Every command, mode, and flag.

## Command syntax

```
optimuspy <mode> <cube_config.json> [options]
```

| Mode | Purpose |
|---|---|
| `optimize` | Benchmark dimension orders (greedy / predefined / position / dimension) |
| `set` | Apply a specific order without benchmarking |
| `scan` | Discover candidate cubes in an instance |
| `optimize-db` | Apply the heuristic order to every cube in an instance under a time limit |

## Global options

| Option | Default | Description |
|---|---|---|
| `--config <path>` | `config/config.ini` | Path to TM1 connection config |
| `-p <password>` | (from config.ini) | Override password for the active instance |
| `--no-resume` | (off) | Ignore any existing checkpoint and start fresh (`optimize` mode; unrelated to `optimize-db --resume`) |

## `optimize` mode

```bash
optimuspy optimize my_cube.json
optimuspy optimize my_cube.json --config config/production.ini
optimuspy optimize my_cube.json -p mypassword
```

The behavior (greedy vs predefined vs position vs dimension) is determined by the JSON config:

- **Greedy** — no special field
- **Predefined** — `predefined_orders` is set
- **Position** — `optimize_position` is set
- **Dimension** — `optimize_dimension` is set

Mutually exclusive — only one of `predefined_orders` / `optimize_position` / `optimize_dimension` may be set.

## `set` mode

```bash
optimuspy set apply_sales.json
```

Requires `predefined_orders` with **exactly one** entry — the order to apply. No iterations, no measurements.

## `scan` mode

```bash
optimuspy scan --instance tm1srv01
optimuspy scan --instance tm1srv01 --output configs/auto/
```

| Option | Description |
|---|---|
| `--instance <name>` | **Required.** Section name in `config.ini`. |
| `--output <dir>` | Generate one JSON config per candidate cube into this directory. |
| `--ram-percent <int>` | RAM threshold (default 60). Cubes accounting for up to this % of total model RAM are listed. |

## `optimize-db` mode

```bash
optimuspy optimize-db instructions.json --dry-run
optimuspy optimize-db instructions.json
optimuspy optimize-db --plan results/tm1srv01/optdb_plan_tm1srv01_2026-09-18_22-00-00.json
optimuspy optimize-db --resume tm1srv01_2026-09-18_22-00-00 --instance tm1srv01
optimuspy optimize-db --restore-chores tm1srv01_2026-09-18_22-00-00 --instance tm1srv01
```

Instance-scoped: the instructions JSON is **not** the cube config schema. Nothing is benchmarked — every cube gets the cardinality heuristic applied once, one cube at a time, until the time limit is reached.

| Option | Description |
|---|---|
| `--dry-run` | Build and print the plan without touching the server. Writes the plan artifact only. |
| `--plan <path>` | Execute a plan file produced by an earlier run instead of building one from instructions. |
| `--resume <plan-id>` | Continue an interrupted run against its **original** deadline. Requires `--instance`. |
| `--restore-chores <plan-id>` | Re-activate the chores a crashed run left disabled — exactly the set that run recorded in its run artifact, not the plan's snapshot. Requires `--instance`. |
| `--instance <name>` | Section name in `config.ini`. Required by `--resume` and `--restore-chores`, which have no instructions file to read it from; taken from the instructions or the plan otherwise. |

Exit code is `0` when the run completed or stopped on the time limit, `1` otherwise.

[Full details → Optimize DB Mode](../modes/optimize-db.md)

## Module mode

```bash
python -m optimuspy optimize my_cube.json
```

Identical behavior to the `optimuspy` console script — useful when the script is not on `PATH`.

## Web UI

```bash
python -m optimuspy.ui                   # default localhost:8765
python -m optimuspy.ui --port 9000
python -m optimuspy.ui --config production.ini
```

[UI Overview →](../ui/overview.md)

## Backward-compatible script entry

For installations from source without `pip install -e .`:

```bash
python optimuspy.py optimize my_cube.json
python ui.py
```

Both wrappers call into the same `optimuspy` package.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Validation failure or runtime error |
| `2` | TM1 connection failure |

Exit codes are useful in CI/CD pipelines and shell loops over multiple configs.

# CLI Reference

Every mode and flag of the `optimuspy` command, on one page. If you're scripting runs (e.g., a shell loop over several cube configs, or a TI process calling OptimusPy), this is the page to keep open.

## Command syntax

```
optimuspy <mode> [cube_config.json] [options]
```

| Mode | Purpose |
|---|---|
| `optimize` | Benchmark dimension orders (greedy / predefined / position / dimension) |
| `set` | Apply a specific order without benchmarking |
| `scan` | Discover candidate cubes in an instance |
| `optimize-db` | Apply the heuristic order to every cube in an instance under a time limit |
| `ui` | Open the web UI (takes only `--port` and `--config`) |

## Global options

These work in every mode except `ui`, which has its own two options (see below).

| Option | Default | Description |
|---|---|---|
| `--config <path>` | `config/config.ini` | Path to the TM1 connection config. An explicit path is treated as read-only, so it can be shared with other tools. |
| `-p`, `--password <password>` | (from config.ini) | Override the password for the active instance. Taken as plain text. |
| `-v`, `--verbose` | (off) | Log at DEBUG level. This is where you see the reason behind every skipped dimension order. |

## `optimize` mode

```bash
optimuspy optimize my_cube.json
optimuspy optimize my_cube.json --config config/production.ini
optimuspy optimize my_cube.json -p mypassword
optimuspy optimize my_cube.json --no-resume
```

| Option | Default | Description |
|---|---|---|
| `--no-resume` | (off) | Ignore any existing checkpoint and start fresh (unrelated to `optimize-db --resume`). |
| `--tm1-checkpoint` | (off) | Store the checkpoint as a TM1 blob (`optimuspy_checkpoint_<cube>.json`) instead of a local file, for environments with no persistent disk. See [Checkpoints & Resume](checkpoints-resume.md#stateless-environments). |

The behavior (greedy vs predefined vs position vs dimension) is decided by the JSON config, not by a flag:

- **Greedy**: no special field
- **Predefined**: `predefined_orders` is set
- **Position**: `optimize_position` is set
- **Dimension**: `optimize_dimension` is set

Only one of `predefined_orders` / `optimize_position` / `optimize_dimension` may be set; two at once is a config error.

## `set` mode

```bash
optimuspy set apply_sales.json
```

Requires `predefined_orders` with **exactly one** entry (the order to apply). No iterations, no measurements. See [Set Mode](../modes/set-mode.md).

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

Instance-scoped: the instructions JSON is **not** the cube config schema. Nothing is benchmarked; every cube gets the cardinality heuristic applied once, one cube at a time, until the time limit is reached.

| Option | Description |
|---|---|
| `--dry-run` | Build and print the plan without touching the server. Writes the plan artifact only. |
| `--plan <path>` | Execute a plan file produced by an earlier run instead of building one from instructions. |
| `--resume <plan-id>` | Continue an interrupted run against its **original** deadline. Requires `--instance`. |
| `--restore-chores <plan-id>` | Re-activate the chores a crashed run left disabled (exactly the set that run recorded in its run artifact, not the plan's snapshot). Requires `--instance`. |
| `--instance <name>` | Section name in `config.ini`. Required by `--resume` and `--restore-chores`, which have no instructions file to read it from; taken from the instructions or the plan otherwise. |

Exit code is `0` when the run completed or stopped on the time limit, `1` otherwise.

[Full details → Optimize DB Mode](../modes/optimize-db.md)

## `ui` mode

```bash
optimuspy ui                    # default http://127.0.0.1:8765
optimuspy ui --port 9000
optimuspy ui --config production.ini
```

The bundled executable opens the UI when it's double-clicked, which is the same as running it with `ui`. `python -m optimuspy.ui` takes the same two options.

[UI Overview →](../ui/overview.md)

## Module mode

```bash
python -m optimuspy optimize my_cube.json
```

Identical behavior to the `optimuspy` console script, which is handy when the script isn't on `PATH`.

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
| `0` | Success. For `set`, this includes an order that was skipped because it would move the locked last slot (the log says `REORDER SKIPPED`). |
| `1` | A config error (missing field, unknown instance, malformed order), a missing `--config` file, or a runtime error during the run. |
| `2` | A usage error: an unknown mode, or a required argument missing (e.g., `scan` without `--instance`). Reported by the argument parser before anything connects. |

One thing to bear in mind is that a TM1 connection failure (wrong credentials, server down) ends the run with a traceback and exit code `1`, not `2`. In a shell loop, checking for a non-zero code is enough; if you also want to catch a skipped `set`, grep the log for `REORDER SKIPPED`.

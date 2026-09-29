<div class="optimus-banner" markdown>
# What's New in 2.0.0

OptimusPy 2.0.0 is a rewrite: a web UI, a JSON-driven command line, several views and TI processes per run, an interactive HTML report, checkpoint and resume, TM1 v12 support, and bundles that run without Python.

[← Back to the landing page](https://cubewise-code.github.io/optimus-py/){ .back-link }
</div>

The main goal of 2.0.0 is that finding a better dimension order becomes a repeatable, auditable workflow rather than a one-off script run. In 1.x you described a run with command-line flags; in 2.0.0 each cube is described in a JSON file you can keep, share and run again, or you drive the whole thing from a local web UI. This page is the tour; the [CHANGELOG](https://github.com/cubewise-code/optimus-py/blob/master/CHANGELOG.md) is the record.

New to OptimusPy? We'd recommend starting with the [User Guide](guide/choose-a-mode.md) instead, because it walks you through a first run end to end.

## New

- **Web UI.** Start it with `optimuspy ui`, or double-click the executable. It opens at `http://127.0.0.1:8765` with these pages: Optimize, Reports, Sync Order, Optimize DB and Settings, plus a Jobs list. See the [UI Overview](ui/overview.md).
- **Modes.** `optimize` benchmarks orders for one cube, in one of four ways: [Greedy](modes/optimize-mode.md) (with an optional Fast mode), [Predefined](modes/predefined-orders.md) (orders you list), [Position](modes/position-optimization.md) (the best dimension for one slot) and [Dimension](modes/dimension-optimization.md) (the best slot for one dimension). Alongside it, [`set`](modes/set-mode.md) applies one order without benchmarking, [`scan`](modes/scan-mode.md) lists the cubes worth optimizing, and [`optimize-db`](modes/optimize-db.md) reorders every cube on an instance by leaf-element count within a time limit, benchmarking nothing.
- **Several views and TI processes per run.** `views` and `processes` take lists, and `process_parameters` sets parameters per process. Each runs `executions` times, and the median counts, so one slow execution doesn't skew the result. See [Multi-View / Multi-Process](advanced/multi-view-multi-process.md).
- **A cardinality-aware greedy.** The search uses each dimension's leaf count to skip the orders that theory rules out by a wide margin, and only measures the ones that are genuinely close. A dimension far larger than the rest is placed once rather than tested everywhere. See [Cardinality-Aware Greedy](concepts/cardinality-aware-greedy.md).
- **Dimension position rules.** `dimension_position_rules` keeps a dimension at a fixed position while the rest are tested, and `orders_to_ignore` skips orders you don't want tested. See [Dimension Position Rules](advanced/dimension-position-rules.md).
- **An HTML report for every run.** Summary cards, the recommended order, a chart of memory against query time relative to the original order, a podium with the best order per metric, and the full sortable table. See the [Reports Page](ui/reports-page.md).
- **Checkpoint and resume.** Run the same `optimize` command again and it continues where a stopped or failed run left off, including the order that was in flight. `--no-resume` starts over, and `--tm1-checkpoint` keeps the checkpoint in TM1's file storage for environments without a persistent disk. See [Checkpoints & Resume](advanced/checkpoints-resume.md).
- **Sync Order and exported orders.** The Sync Order page copies storage orders from one instance to another, and can export them to `exports/` as JSON configs that `optimuspy set` applies. See the [Sync Order Page](ui/sync-order-page.md) and [Exporting & Importing Orders](advanced/exporting-importing-orders.md).
- **Settings page.** It links the `config.ini` you already keep for RushTI or your scripts, or copies it into `config/config.ini`, then shows each instance read-only with *Test Connection*. The choice is shared with the CLI. See the [Settings Page](ui/settings-page.md).
- **A settings file.** `config/settings.ini` remembers the linked `config.ini`, the UI's port and whether it opens a browser. It's optional; the bundle ships `config/settings.ini.example`. See [Settings File](getting-started/settings.md).
- **TM1 v12 (PAoC / PAaaS)** alongside v11. Memory is read through TM1py's Metrics service on both, and the VMM / VMT override only happens on v11, where those settings exist. See [VMM / VMT Handling](concepts/vmm-vmt-handling.md).
- **`-v` / `--verbose`** logs the reason each skipped order was refused. See [Optimization Logging](concepts/how-it-works.md#optimization-logging).
- **Windows and Linux bundles.** Each holds the executable, `config/config.ini.example`, `config/settings.ini.example` and the sample cube configs, so nothing needs installing. See [Installation](getting-started/installation.md).

## Changed

- **Command line.** The command is now `optimuspy <mode> <cube_config.json>` (or `python -m optimuspy`, or `python optimuspy.py` from a clone), and the 1.x flags are gone. See the [CLI Reference](advanced/cli-reference.md).
- **Where `config.ini` lives.** It's read from the file given with `--config`, else the file linked on the Settings page, else `config/config.ini` in the folder you run from (for the bundle, the executable's folder). OptimusPy doesn't edit it, so it can be shared with other TM1py tools. See [TM1 Connection](getting-started/tm1-connection.md#which-configini-is-read).
- **Where the log is written.** `logs/optimuspy.log` in the install folder: the executable's folder for the bundle, the repository root for a clone. 1.x wrote `optimuspy.log` in the folder you ran from.
- **Result files.** They go in `results/<instance>/`, named `<instance>_<cube>_<timestamp>`, without the view or process in the name. An HTML report is always written, and it replaces the 1.x `.png` chart.
- **Python 3.9 or later**, installed with pip along with the dependencies (TM1py 2.3.0 or later). matplotlib and seaborn are no longer needed.

## Removed

- **Benchmarking every cube with one command.** In 1.x, leaving out `-c` benchmarked every cube that had the given view. 2.0.0 benchmarks one cube per config. To cover a whole instance, use `scan --output` to write a config for each candidate cube, or run `optimize-db`, which reorders every cube but benchmarks nothing.

## Upgrading from 1.x

1. **Install 2.0.0.** Unzip the Windows or Linux bundle, or with Python 3.9 or later clone the repository and run `pip install -e .`. See [Installation](getting-started/installation.md).
2. **Move `config.ini` into a `config` folder.** 2.0.0 reads `config/config.ini`; a `config.ini` sitting next to the executable is not read. The instance sections keep the same format. To leave the file where it is, pass `--config path/to/config.ini`.
3. **Turn each command into a JSON cube config.** A 1.x command stops with `error: unrecognized arguments` or `invalid choice`, exit code 2, before it connects. For example, this 1.x command:

    ```
    optimuspy.py -i my_instance -c Sales -v Optimus -e 10 -f True -o csv -u True -t load.csv.file -d Time,Version
    ```

    becomes `optimuspy optimize sales.json`, where `sales.json` contains:

    ```json
    {
      "instance": "my_instance",
      "cube": "Sales",
      "views": ["Optimus"],
      "processes": ["load.csv.file"],
      "executions": 10,
      "fast": true,
      "output": "csv",
      "update": true,
      "dimensions_to_exclude": ["Time", "Version"]
    }
    ```

    | 1.x flag | 2.0.0 |
    |---|---|
    | `-i`, `--instance` | `"instance"` |
    | `-c`, `--cube` | `"cube"`, now required (see *Removed*) |
    | `-v`, `--view` | `"views"`, a list. On the command line, `-v` now means `--verbose` |
    | `-e`, `--executions` | `"executions"`, now required (1.x defaulted to 15) |
    | `-d`, `--dimensions_to_exclude` | `"dimensions_to_exclude"`, a list instead of a comma-separated string |
    | `-f`, `--fast` | `"fast"`, `true` or `false` |
    | `-o`, `--output` | `"output"`, `"csv"` or `"xlsx"`, now required. On the command line, `--output` is now scan's folder for generated configs |
    | `-u`, `--update` | `"update"` (or `"auto_apply"`) |
    | `-p`, `--password` | Unchanged: `-p` / `--password` on the command line |
    | `-t`, `--process` | `"processes"`, a list |

    Every field is listed in the [JSON Config Reference](advanced/json-config-reference.md).
4. **Look for results in a folder per instance.** Each run writes `results/<instance>/<instance>_<cube>_<timestamp>.html`, plus a `.csv` or `.xlsx` of the same name. See the [Reports Page](ui/reports-page.md).

## Design notes

The pages above describe how to use each feature. For the reasoning behind the bigger design decisions (the order frame and the locked slot, the Optimize DB pass, the checkpoint format, position rules, and what changes between v11 and v12), see the [Design Notes](design/order-frame.md) section.

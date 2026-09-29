# Changelog

## 2.0.0

OptimusPy finds a better storage dimension order for your TM1 cubes and can apply it. In 2.0.0 you work either in a web UI or on the command line, where each cube is described in a JSON file you can keep and run again. It supports TM1 v11 and v12, and it ships as a Windows or Linux bundle that runs without Python. New to OptimusPy? Start with the [User Guide](docs/guide/choose-a-mode.md).

### Upgrading from 1.x

1. **Install 2.0.0.** Unzip the Windows bundle (`optimuspy-windows.zip`) or the Linux bundle (`optimuspy-linux.tar.gz`). Its `optimuspy` folder holds the executable, `config/config.ini.example` and `samples/` (example cube configs). With Python 3.9 or later you can instead clone the repository and run `pip install -e .`, which adds the `optimuspy` command. See [Installation](docs/getting-started/installation.md).
2. **Move `config.ini` into a `config` folder.** 2.0.0 reads `config/config.ini`, relative to the folder you run the command from (for the bundle, the executable's folder). A `config.ini` sitting in that folder itself is not read. The instance sections keep the same format. To leave the file where it is, link it from the [Settings page](docs/ui/settings-page.md), which the command line then uses too, or pass `--config path/to/config.ini`. Either way OptimusPy only reads that file and never writes to it. See [TM1 Connection](docs/getting-started/tm1-connection.md).
3. **Turn each command into a JSON cube config.** The 1.x flags are gone. A 1.x command stops with `error: unrecognized arguments` or `invalid choice`, exit code 2, before it connects. For example, this 1.x command:

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

    Every field is listed in the [JSON Config Reference](docs/advanced/json-config-reference.md).
4. **Look for results in a folder per instance.** Each run writes `results/<instance>/<instance>_<cube>_<timestamp>.html`, plus a `.csv` or `.xlsx` of the same name, relative to the folder you run from (for the bundle, the executable's folder). 1.x wrote `results/<instance>_<cube>_<view>_<process>_<timestamp>` as `.csv` or `.xlsx`, plus a `.png` chart. See [Results Page](docs/ui/results-page.md).

### New

- **Web UI.** Start it with `optimuspy ui`, or double-click the executable. It opens at `http://127.0.0.1:8765` and has these pages: Optimize, Results, Sync Order, Optimize DB and Settings, plus a Jobs list. See [UI Overview](docs/ui/overview.md).
- **Modes.**
  - `optimize` benchmarks orders for one cube, in one of these modes:
    - Greedy (with an optional Fast mode);
    - [Predefined](docs/modes/predefined-orders.md): orders you list;
    - [Position](docs/modes/position-optimization.md): the best dimension for one slot;
    - [Dimension](docs/modes/dimension-optimization.md): the best slot for one dimension.

    See [Optimize Mode](docs/modes/optimize-mode.md).
  - [`set`](docs/modes/set-mode.md) applies one order without benchmarking.
  - [`scan`](docs/modes/scan-mode.md) lists the cubes that make up `--ram-percent` of the instance's memory (60% by default), largest first. With `--output`, it also writes a starter config for each cube.
  - [`optimize-db`](docs/modes/optimize-db.md) reorders every cube on an instance by leaf-element count, fewest first, within a time limit. It benchmarks nothing, and it leaves already optimized cubes (a storage order that differs from the presentation order) alone unless `include_optimized` is set. With `disable_active_chores`, it disables the chores that are active when the run starts and re-enables them afterwards.
    - `--dry-run` builds the plan without changing anything.
    - `--plan` runs a saved plan.
    - `--resume` continues a stopped run in the time left.
    - `--restore-chores` re-enables chores that a crashed run left disabled.
- **Several views and TI processes per run.** `views` and `processes` take lists, and `process_parameters` sets parameters for each process. Each one runs `executions` times, and the median counts. See [Multi-View / Multi-Process](docs/advanced/multi-view-multi-process.md).
- **Dimension position rules.** `dimension_position_rules` keeps a dimension at a fixed position while the rest are tested, and `orders_to_ignore` skips orders you don't want tested. See [Dimension Position Rules](docs/advanced/dimension-position-rules.md).
- **HTML report for every run.** It shows summary cards, the recommended order, a chart of memory against query time relative to the original order, the best orders, and the full table. See [Results Page](docs/ui/results-page.md).
- **Checkpoint and resume.** Run the same `optimize` command again and it continues where a stopped or failed run left off. `--no-resume` starts over. `--tm1-checkpoint` keeps the checkpoint in TM1's file storage instead of a local file, for environments without local storage such as Atmosphere. See [Checkpoints & Resume](docs/advanced/checkpoints-resume.md).
- **Sync Order and exported orders.**
  - The Sync Order page copies storage orders from one instance to another.
  - It can also export them to `exports/` as JSON cube configs that `optimuspy set` applies.

  See [Sync Order Page](docs/ui/sync-order-page.md) and [Exporting & Importing Orders](docs/advanced/exporting-importing-orders.md).
- **Settings page.** It links the `config.ini` you already keep for RushTI or your scripts, or copies it into `config/config.ini`, and shows each instance read-only with *Test Connection*. The CLI uses the same file. See [Settings Page](docs/ui/settings-page.md).
- **A settings file.** The optional `config/settings.ini` remembers the linked `config.ini`, the UI's port and whether it opens a browser. The bundle ships `config/settings.ini.example`. See [Settings File](docs/getting-started/settings.md).
- **Folders chosen in Settings.** Saved cube configs go to `cube-configs/` and Sync Order exports to `exports/`; the Settings page moves either one.
- **TM1 v12 (PAoC / PAaaS)** alongside v11. VMM and VMT are raised during a run and put back afterwards on v11 only. See [Home](docs/index.md).
- **`-v` / `--verbose`** logs the reason each skipped order was refused.
- **Windows and Linux bundles.** Each holds the executable, `config/config.ini.example`, `config/settings.ini.example` and the sample cube configs. See [Installation](docs/getting-started/installation.md).

### Changed

- **Command line.** The command is now `optimuspy <mode> <cube_config.json>` (or `python -m optimuspy`, or `python optimuspy.py` from a clone), and the 1.x flags are gone. See [CLI Reference](docs/advanced/cli-reference.md).
- **Where `config.ini` lives.** It is read from the file given with `--config`, else the file linked on the Settings page, else `config/config.ini` in the folder you run from (for the bundle, the executable's folder). OptimusPy doesn't edit it.
- **Where the log is written.** OptimusPy writes `logs/optimuspy.log` in its install folder: the executable's folder for the bundle, the repository root for a clone. 1.x wrote `optimuspy.log` in the folder you ran from.
- **Result files.** They go in a folder per instance, and the names no longer include the view or process. An HTML report is always written, and it replaces the 1.x `.png` chart.
- **Python 3.9 or later.** You install with pip, which also installs the dependencies (TM1py 2.3.0 or later). matplotlib and seaborn are no longer needed.

### Removed

- **Benchmarking every cube with one command.** In 1.x, leaving out `-c` benchmarked every cube that had the given view. 2.0.0 benchmarks one cube per config. To cover a whole instance, use `scan --output` to write a config for each candidate cube, or run `optimize-db`, which reorders every cube but benchmarks nothing.

Releases before 2.0.0 are listed on the [GitHub Releases page](https://github.com/cubewise-code/optimus-py/releases).

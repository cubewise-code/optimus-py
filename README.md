
![](https://github.com/cubewise-code/optimus-py/blob/master/images/logo.png)

# OptimusPy for TM1

Find the ideal dimension order for your TM1 cubes

Supported versions: TM1 v11 and v12 (PAoC/PAaaS).

What's new in 2.0.0, and how to upgrade from 1.x: [CHANGELOG.md](CHANGELOG.md).

## Installing

- **Without Python:** download the Windows or Linux bundle. Each holds the executable, `config/config.ini.example` and `samples/` (example cube configs).
- **With Python 3.9 or later:** clone the repository and run `pip install -e .`, which installs the dependencies and adds the `optimuspy` command.

Both are described step by step in [Installation](https://cubewise-code.github.io/optimus-py/getting-started/installation/).

## Usage

Describe the cube in a JSON file, then run it:

```bash
optimuspy optimize samples/optimize.json
```

Or open the web UI at `http://127.0.0.1:8765` (double-clicking the executable does the same):

```bash
optimuspy ui
```

Every mode, option and JSON field is documented on the [documentation site](https://cubewise-code.github.io/optimus-py/).

## Modes

| Mode | Purpose |
|---|---|
| `optimize` | Benchmark dimension orders for one cube and report the best one |
| `set` | Apply a specific order to one cube without benchmarking |
| `scan` | Discover candidate cubes in an instance, ranked by RAM |
| `optimize-db` | Reorder every cube in an instance with one simple rule — dimensions ordered by leaf-element count, fewest first — within a time limit. Nothing is benchmarked. Run it overnight on a dedicated instance, restart TM1, then run the real `optimize` exercise against a smaller footprint |
| `ui` | Open the web UI (its options: `--port`, `--config`) |

```bash
optimuspy optimize my_cube.json
optimuspy set apply_sales.json
optimuspy scan --instance tm1srv01
optimuspy optimize-db instructions.json --dry-run
```

## Config file (`--config`)

Both the CLI (`optimuspy`) and the web UI (`python -m optimuspy.ui`) accept a `--config PATH` option pointing at a TM1 connection `config.ini`:

```bash
optimuspy scan --instance tm1srv01 --config C:\shared\config.ini
python -m optimuspy.ui --config C:\shared\config.ini
```

- **Default** (flag omitted): `config/config.ini`, fully writable — the UI's Settings page can create, edit, and delete instances in it.
- **Explicit path** (`--config` supplied): treated as owned by another tool and **read-only** — OptimusPy never writes to it. This lets you point OptimusPy at a `config.ini` shared with other tm1py tools (e.g. RushTI) without duplicating credentials. In the UI, the Settings page shows a read-only banner and hides the create/edit/delete controls for that file (Test Connection still works).
- If the path passed to `--config` does not exist, OptimusPy prints `ERROR: config.ini not found: <path>` and exits immediately (exit code 1).

## Output

Each run writes an HTML report to `results/<instance>/`, in the folder you run from, plus a `.csv` or `.xlsx` of the same name (the config's `output` field). See [Results Page](https://cubewise-code.github.io/optimus-py/ui/results-page/).

## Considerations
- Ideally run on the same machine as TM1
- Use big and representative views _(e.g. typical slices that end users consume)_
- Choose a sensible number of `executions` between 5 and 10
- Provide enough spare memory on TM1 server
- Fast mode (`fast: true`) starts from the order the leaf counts suggest, then only tests moves for dimensions whose leaf counts are close to each other. It needs fewer reorders than the default search, which is more thorough.
- Choose a TI that loads data to the cube and runs for at least a few seconds

## Executable bundles

The **Build Executable** workflow builds a Windows and a Linux bundle on every run and keeps them as the `optimuspy-windows` and `optimuspy-linux` artifacts of that run, on the [Actions tab](https://github.com/cubewise-code/optimus-py/actions). Builds from `master` also publish `optimuspy-windows.zip` and `optimuspy-linux.tar.gz` on the [Releases page](https://github.com/cubewise-code/optimus-py/releases). See [Installation](https://cubewise-code.github.io/optimus-py/getting-started/installation/).

## Built With

* [TM1py](https://github.com/cubewise-code/TM1py) - A python wrapper for the TM1 REST API
* [mdxpy](https://pypi.org/project/mdxpy/)
* [pandas](https://pypi.org/project/pandas/)
* [XlsxWriter](https://pypi.org/project/XlsxWriter/)
* [configparser](https://pypi.org/project/configparser/)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details

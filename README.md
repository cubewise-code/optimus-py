![](https://github.com/cubewise-code/optimus-py/blob/master/images/logo.png)

# OptimusPy for TM1

Find the ideal dimension order for your TM1 cubes

OptimusPy finds a better storage dimension order for a TM1 cube by applying real reorders on the server and measuring memory, query time and TI time for each. It reports the best order and can apply it for you. It supports TM1 v11 and v12 (PAoC/PAaaS).

## Setup

1. **Install.** Either:
    - download the Windows (`optimuspy-windows.zip`) or Linux (`optimuspy-linux.tar.gz`, or `optimuspy-linux-arm64.tar.gz` on ARM) bundle from the [Releases page](https://github.com/cubewise-code/optimus-py/releases) and unpack it. It holds the executable, `config/config.ini.example` and `samples/` (example cube configs). No Python needed;
    - or, with Python 3.9 or later, clone the repository and run `pip install -e .`, which adds the `optimuspy` command.

    See [Installation](https://cubewise-code.github.io/optimus-py/docs/getting-started/installation/).
2. **Connect to TM1.** Copy `config/config.ini.example` to `config/config.ini` and add a section for your instance. If you already keep a `config.ini` for RushTI or your scripts, link it on the UI's *Settings* page instead. See [TM1 Connection](https://cubewise-code.github.io/optimus-py/docs/getting-started/tm1-connection/).

## Run it in the UI

```bash
optimuspy ui
```

Or double-click the executable. The UI opens at `http://127.0.0.1:8765`. Then:

1. Choose your instance in the sidebar.
2. On the *Optimize* page, click a cube.
3. On *Configure*, keep *Greedy*, pick a view and click *Save & Start Optimization*.
4. When it ends, open the HTML report on the cube's *Results* tab.

## Run it on the command line

Describe the cube in a JSON file, like `samples/optimize.json`:

```json
{
  "instance": "tm1srv01",
  "cube": "Sales",
  "views": ["Optimus"],
  "processes": [],
  "executions": 10,
  "fast": false,
  "output": "csv",
  "update": false,
  "dimensions_to_exclude": [],
  "predefined_orders": [],
  "orders_to_ignore": []
}
```

Then run it:

```bash
optimuspy optimize samples/optimize.json
```

The report is written to `results/<instance>/`. With `"update": false` the cube ends in its original order.

To find which cubes are worth optimizing, scan the instance. This lists the largest cubes, the ones that make up 60% of its memory, leaves out those already optimized, and writes a starter config for each into `cube-configs/`; add your views to each file before you run it:

```bash
optimuspy scan --instance tm1srv01 --output cube-configs/
```

## Documentation

**[cubewise-code.github.io/optimus-py/docs](https://cubewise-code.github.io/optimus-py/docs/)**

- New to OptimusPy? Start with the [User Guide](https://cubewise-code.github.io/optimus-py/docs/guide/choose-a-mode/).
- What's new in 2.0.0, and how to upgrade from 1.x: [CHANGELOG.md](CHANGELOG.md).

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details

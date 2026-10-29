<div class="optimus-banner" markdown>
# Quick Start

Get from a fresh install to your first optimized cube in about 10 minutes.

[← Back to the landing page](https://cubewise-code.github.io/optimus-py/){ .back-link }
</div>

1. **Open the UI.** Double-click the executable, or run `optimuspy ui`. It opens at `http://127.0.0.1:8765`.
2. **Add your server.** Copy `config/config.ini.example` to `config/config.ini` and fill in `address`, `port`, `user`, `password` and `ssl`. If you already keep a `config.ini` for RushTI or your scripts, link it on the *Settings* page instead. See [TM1 Connection](tm1-connection.md) for every parameter.
3. **Pick a cube.** Choose the instance in the sidebar. The *Optimize* page lists the biggest cubes, up to 60% of the instance's memory (move the *RAM Threshold* slider to see more); click one.
4. **Run it.** On *Configure*, keep *Greedy*, pick a view and click *Save & Start Optimization*. When it ends, open the HTML report from the cube's *Reports* tab.

![OptimusPy Home page on first launch, with the instance tiles and Tips & Getting Started](../assets/images/optimuspy/ui/optimize-page.png)

The full walkthrough, in the UI and on the command line, is in the User Guide: [Your First Optimization →](../guide/first-optimization.md)

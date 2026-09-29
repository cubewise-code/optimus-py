# Optimize DB Step by Step

Every cube overnight.

Optimize DB doesn't benchmark. It sorts each cube's dimensions by leaf count, fewest first, and keeps the change only if the cube didn't use more memory (`revert_on_regression`, on by default). Use it to shrink a whole instance cheaply, then run `optimize` on the cubes that matter most.

<div class="diagram-frame">
  <iframe src="../diagrams/optimize-db-run.html" title="Steps of an Optimize DB run" loading="lazy"></iframe>
</div>

[Open the diagram full screen](diagrams/optimize-db-run.html){ target=_blank }

## In the UI

1. Open *Optimize DB*, choose the instance and set the options: time limit, minimum cube size, cubes to exclude, and whether to disable active chores for the run.
2. Click *Build plan*. Nothing on the server changes. Review the cubes it will reorder, their new orders, and the cubes it skips and why.
3. Click *Run plan* and confirm. Progress shows cube by cube. *Stop after current cube* ends the run once the cube in progress finishes.
4. After a stop or the time limit, *Previous runs* offers *Resume*, which continues in the time that was left. If a run ended without re-enabling chores, the page offers *Re-enable chores*.
5. See the outcome in the run's report: *Report* in *Previous runs*, or the run under *Optimize DB (all cubes)* on the [Reports page](../ui/reports-page.md). It lists what was reordered, reverted or failed, and the expected saving.

## On the command line

```bash
optimuspy optimize-db instructions.json --dry-run     # build and print the plan, change nothing
optimuspy optimize-db instructions.json               # build and run
optimuspy optimize-db --plan <plan file>              # run a plan you reviewed
optimuspy optimize-db --resume <plan id>              # continue a stopped run
optimuspy optimize-db --restore-chores <plan id>      # re-enable chores a crashed run left off
```

`samples/optimize_db.json` shows every option. The plan, the run and the report are written to `results/<instance>/`, and the run summary ends with the report's path.

!!! note
    After an Optimize DB run, restart TM1 before you benchmark cubes with `optimize`.

Every option is explained on [Optimize DB Mode](../modes/optimize-db.md), and every control of the page on the [Optimize DB Page](../ui/optimize-db-page.md).

**Back to the start:** [Choose a Mode](choose-a-mode.md)

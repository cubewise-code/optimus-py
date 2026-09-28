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

## On the command line

```bash
optimuspy optimize-db instructions.json --dry-run     # build and print the plan, change nothing
optimuspy optimize-db instructions.json               # build and run
optimuspy optimize-db --plan <plan file>              # run a plan you reviewed
optimuspy optimize-db --resume <plan id>              # continue a stopped run
optimuspy optimize-db --restore-chores <plan id>      # re-enable chores a crashed run left off
```

`samples/optimize_db.json` shows every option. The plan and run files are written to `results/<instance>/`.

!!! note
    After an Optimize DB run, restart TM1 before you benchmark cubes with `optimize`.

Every option is explained on [Optimize DB Mode](../modes/optimize-db.md).

**Next:** [Taking an Order to Production →](taking-an-order-to-production.md)

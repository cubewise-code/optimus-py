# Results Page

All optimization runs write artifacts to the local `results/` directory, in a folder per instance. The Results page lists them with most recent first and lets you open each file.

![Results page listing the CSV and HTML files of one optimization, with instance, cube, type, size and date](../assets/images/optimuspy/ui/results-page.png)

## Result file types

Every successful run generates one HTML report. Depending on the `output` field in your config, you also get a CSV or an XLSX with the raw data.

| Extension | Purpose |
|---|---|
| `.html` | Interactive report with podium + scatter chart |
| `.csv` | One row per tested permutation, all metrics, after four `#` comment lines and a blank line (skip them if you import the file) |
| `.xlsx` | Same rows as the CSV on one sheet, with the original and best orders shaded |

Files are named `results/{instance}/{instance}_{cube}_{YYYY-MM-DD_HH-MM-SS}.{ext}` so they sort chronologically.

## Reading the HTML report

Open any `.html` file. Below the summary cards and the recommended dimension order, the report has three parts:

### Scatter chart (Chart.js)

Every tested permutation plotted on RAM (X) vs query time relative to the original order (Y). Hover any dot for the full order. The original order is marked in a contrasting color. One thing to bear in mind is that the chart library loads from a CDN, so this part of the report needs internet access; the podium and the table are self-contained.

![Scatter chart of every tested order, RAM against query time relative to the original, with the original order and the result marked](../assets/images/optimuspy/report/report-scatter.png)

### Podium

Cards side by side, above the table: **Best Overall**, then **#1 Fastest Query** (when views were benchmarked), **#1 Fastest Process** (when processes were) and **#1 Lowest RAM**. Click a card to highlight its row in the table. If no order qualified as Best Overall, there's no podium, and the log asks you to pick from the results.

![Report podium with the Best Overall, #1 Fastest Query and #1 Lowest RAM cards](../assets/images/optimuspy/report/report-podium.png)

### Detail table

Every permutation, sortable. Use this when you want to dig into the raw numbers: query time and process time with their ratio to the original, RAM and its reduction, reorder time, and the dimension order.

## Downloading CSV / XLSX

Click a row's **Open** button. CSVs open in Excel / Numbers / your editor of choice. An XLSX file has one sheet: a short header (instance, cube, generation time), then one row per tested permutation.

## Where results live on disk

```
results/
└── tm1srv01/
    ├── tm1srv01_Sales_2026-04-01_15-23-44.html
    ├── tm1srv01_Sales_2026-04-01_15-23-44.csv
    └── tm1srv01_Budget_2026-04-01_16-02-11.html
```

Files are never auto-deleted, so clean up old runs by hand.

## Checkpoint files

Files named `checkpoint_*.json` in `results/` are mid-run state snapshots used by the resume feature. They're hidden from the Results page list. See [Checkpoints & Resume](../advanced/checkpoints-resume.md).

# Report Periods and Baselines

Reference matrix for period resolution and baseline selection behavior.

| Option                                | Example "today" | Current Range Used for Report | Baseline Range to Find                                  |
| ------------------------------------- | --------------- | ----------------------------- | ------------------------------------------------------- |
| `--yesterday`                         | 2026-04-08      | 2026-04-07 to 2026-04-07      | 2026-04-06 to 2026-04-06                                |
| `--last-week`                         | 2026-04-08      | 2026-03-30 to 2026-04-05      | 2026-03-23 to 2026-03-29                                |
| `--this-week`                         | 2026-04-08      | 2026-04-06 to 2026-04-08      | 2026-03-30 to 2026-04-05                                |
| `--last-month`                        | 2026-04-08      | 2026-03-01 to 2026-03-31      | 2026-02-01 to 2026-02-28                                |
| `--this-month`                        | 2026-04-08      | 2026-04-01 to 2026-04-08      | 2026-03-01 to 2026-03-31                                |
| `--this-month` (31 to 30 days)        | 2026-05-20      | 2026-05-01 to 2026-05-20      | 2026-04-01 to 2026-04-30                                |
| `--this-month` (leap year)            | 2024-03-10      | 2024-03-01 to 2024-03-10      | 2024-02-01 to 2024-02-29                                |
| `--last-year`                         | 2026-04-08      | 2025-01-01 to 2025-12-31      | 2024-01-01 to 2024-12-31                                |
| `--this-year`                         | 2026-04-08      | 2026-01-01 to 2026-04-08      | 2025-01-01 to 2025-12-31                                |
| `--last 7`                            | 2026-04-08      | 2026-04-01 to 2026-04-07      | 2026-03-25 to 2026-03-31                                |
| `--start 2026-03-07 --end 2026-03-14` | any             | 2026-03-07 to 2026-03-14      | Most recent earlier 8-day range                         |
| `--start 2026-03-07 --end 2026-03-14` | any             | 2026-03-07 to 2026-03-14      | No 8-day range found (comparison skipped)               |
| Any option                            | any             | Current range                 | Same exact dates as current (self-comparison skipped)   |
| Any option                            | any             | Current range                 | Baseline overlaps current (skipped)                     |
| Any option                            | any             | Current range                 | Baseline missing current zone (zone comparison skipped) |
| Any option                            | any             | Current range                 | No valid baseline found after all filters               |

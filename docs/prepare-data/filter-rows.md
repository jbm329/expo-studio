# Filter rows

Filter a result dataset to keep rows that match a column condition or a cell's
value. Filtering removes nonmatching rows from the dataset in the active
result tab; it does not just hide them in the table.

Select a **ready result tab**. You can start a filter from a column header or
from a cell.

To remove repeated records by comparing every column instead of a column
condition, use [Remove duplicate rows](#remove-duplicate-rows) from the result
tab's own context menu.

## Filter from a column header {#filter-from-column-header}

1. Right-click a column header.
2. Open **Filter rows…** and choose an available action.
3. Enter or select any requested value, then confirm.

| Action | Use it to |
|---|---|
| **Equals…** | Keep rows whose value matches a value you enter. Text matching lets you choose whether the match is case-sensitive. |
| **Contains…** | Keep rows whose text contains the search text; choose whether matching is case-sensitive. |
| **Is empty** / **Is not empty** | Keep rows where the column is missing, or where it is not missing. |
| **Compare…** | Compare numeric or datetime values with a selected operator and value. |
| **Between…** | Keep numeric or datetime values within the entered lower and upper bounds; choose whether the bounds are inclusive. |

The comparison and range actions are available for numeric or datetime
columns. The menu enables actions according to the selected column's type.

Comparison filters exclude rows with missing values, including **not equals**
(`!=`). A missing comparison value matches no rows. Use **Is empty** or
**Is not empty** to filter explicitly by missingness.

In this example, **Between…** on **Amount** with bounds `10` and `20` keeps the
two rows whose amounts are between those values:

| Region | Amount |
|---|---:|
| North | 10 |
| South | 20 |

**Is empty** means that the value is missing. It does not mean that a text
value is an empty string. An empty string and a missing value are different.

## Filter from a cell {#filter-from-cell}

Right-click a cell, open **Filter…**, then choose:

- **Keep rows** to keep rows whose value in that column equals the selected
  cell's value.
- **Remove rows** to remove rows whose value in that column equals the
  selected cell's value.

If the selected cell is missing, **Keep rows** keeps rows with missing values
in that column, and **Remove rows** removes rows with missing values. For a
nonmissing selected value, **Remove rows** removes rows whose value in that
column matches the selected value.

When removing a nonmissing selected value, rows with missing values are kept:
only matching rows are removed. For example, removing `1` from a column
containing `1`, `2` and a missing value keeps `2` and the missing row. Using
**Compare… → != 1** instead keeps only `2`.

For example, right-click a cell containing `North` in **Region** and select
**Filter… → Keep rows** to keep the rows where **Region** equals `North`.

## Remove duplicate rows {#remove-duplicate-rows}

1. Right-click the **result tab** for the dataset to change, not a column header
   or cell. The dataset must be ready.
2. Select **Remove duplicate rows**.
3. Wait for the background operation. The status bar reports how many duplicate
   rows were removed, or that no duplicate rows were found. There is no success
   popup.

The action changes the right-clicked dataset in its existing tab, even if a
different tab is active. It does not modify the source file or database or
create a new result tab. The action is unavailable on pending or failed tabs,
or while duplicate removal is already running for that dataset.

Rows are duplicates when **all columns** match under pandas' equality rules.
The first occurrence in the underlying dataset order is retained. A table's
display-only sort does not change that order. Source index labels are not
compared; after removal the result has a new sequential index. Matching missing
values can count as duplicates. Text is not trimmed or case-normalized, and
nested values are not converted to text.

For example, `North, 10`, `North, 10`, `North, 20` becomes
`North, 10`, `North, 20`. Matching only Region is not enough to remove the last
row because Amount differs.

If no duplicates are found, the dataset, its index and undo history are left
unchanged. If the tab closes or its data changes before processing finishes,
the outdated result is not applied. Unsupported values, such as lists or
dictionaries in some multi-column datasets, can cause duplicate removal to
fail. An error dialog reports failures; rows are not silently retained as a
successful result.

Duplicate detection uses the same service as
[duplicate exclusion during concatenation](../transform-data/concatenate.md#exclude-duplicate-rows).
It takes additional processing time and temporary memory, especially for wide
datasets or long text. Computation runs in the background, but applying the
result and preparing an undo snapshot follow the existing preparation workflow
on the GUI thread.

## Review, undo or continue filtering

Each filter changes the current result dataset. A later filter works on the
rows that remain, so successive filters narrow the result further. Use
**Undo** on the toolbar to reverse an available filter or duplicate-removal
operation. Undo is best-effort, just like other preparation actions: existing
[undo settings](../settings/general-settings.md#basic-settings), dataset-size
limits and snapshot availability determine whether a step is retained. An
operation can succeed without an undo step. To undo duplicate removal in a
nonactive tab, select that tab first.

To save the prepared
dataset, select its result tab and export it; see
[Export a dataset](../export-and-report/export-data.md).

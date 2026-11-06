# Filter rows

Filter a result dataset to keep rows that match a column condition or a cell's
value. Filtering removes nonmatching rows from the dataset in the active
result tab; it does not just hide them in the table.

Select a **ready result tab**. You can start a filter from a column header or
from a cell.

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

For example, right-click a cell containing `North` in **Region** and select
**Filter… → Keep rows** to keep the rows where **Region** equals `North`.

## Review, undo or continue filtering

Each filter changes the current result dataset. A later filter works on the
rows that remain, so successive filters narrow the result further. Use
**Undo** on the toolbar to reverse an available filter. To save the prepared
dataset, select its result tab and export it; see
[Export prepared data](../application-overview.md#export-data).

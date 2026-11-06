# Organize columns

Sort rows by a column, rename or remove a column, or change the order of
columns in a result dataset. These actions change the dataset in the active
result tab; they do not edit its source file or database.

Select a **ready result tab**, then right-click the header of the column you
want to work with.

## Sort rows {#sort-rows}

Use this example dataset:

| Region | Amount |
|---|---:|
| North | 30 |
| South | 10 |
| East | 20 |

1. Right-click the **Amount** column header.
2. Select **Sort ascending** to put the smallest values first, or
   **Sort descending** to put the largest values first.

Sorting changes the order of the rows, not the order of the columns. Each
record's values stay together as its row moves.

## Rename a column {#rename-column}

1. Right-click the column header and select **Rename…**.
2. Enter a nonempty name that is not already used by another column.
3. Confirm the change.

Renaming changes the column label, not its values. If the name is already in
use, choose a different name.

## Remove a column {#remove-column}

1. Right-click the column header and select **Remove…**.
2. Confirm that you want to remove the named column.

Removing a column removes its values from the result dataset in this tab.
It does not delete the source file or alter the database table. Use **Undo**
if the removal was a mistake and an undo step is available.

## Change column order {#change-column-order}

1. Right-click a column header and open **Order**.
2. Select **Move left**, **Move right**, **Move to first** or
   **Move to last**.

The options at the beginning or end of the table are unavailable when the
column is already at that boundary. Moving a column changes its position in
the table, not row order or cell values.

## Keep or undo the changes

Review the result after each operation. Use **Undo** on the toolbar to reverse
an available change. To save the prepared dataset, select the result tab and
export it; see [Export prepared data](../application-overview.md#export-data).

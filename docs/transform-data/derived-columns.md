# Derived columns

Create a new column by calculating a value for each row in your dataset.
Your formula can refer to other columns without changing their values.

## Create your first derived column {#create-your-first-derived-column}

This example calculates a line total from a price and a quantity. Start with
a dataset containing these numeric columns:

| Price | Quantity |
|---|---|
| 12.50 | 2 |
| 8.00 | 3 |
| 20.00 | 1 |

1. In the result table, right-click the **Quantity** column header.
2. Select **Derived column…**.
3. In **Column name**, enter `Line total`. Use a name that does not already
   exist in the dataset.
4. In **f(x)**, enter:

   ```text
   [Price] * [Quantity]
   ```

5. Select **OK** to create the column.

The new column appears immediately after the column whose header you
right-clicked. In this example, the result is:

| Price | Quantity | Line total |
|---|---|---|
| 12.50 | 2 | 25 |
| 8.00 | 3 | 24 |
| 20.00 | 1 | 20 |

The table above shows the calculated values; their displayed number formatting
may differ in the application.

### Reading the formula

Square brackets identify column names: `[Price]` means the value in the
**Price** column for the current row. The `*` operator multiplies it by the
value in **Quantity**.

Use the column names from your own dataset when adapting the example.

## Editor assistance {#editor-assistance}

### Column autocomplete

Type `[` in **f(x)** to see available column names. Continue typing to narrow
the suggestions; matching is not case-sensitive. For example, type `[Pri`
to find **Price**.

Select a suggestion with the mouse, or use the arrow keys to highlight it and
press **Enter** or **Tab**. The editor inserts the column reference, including
its brackets. Press **Esc** to dismiss the suggestions without inserting one.

These suggestions complete column names, not function names or entire formulas.

### Checking your formula

The dialog checks your input as you type. Both a column name and a valid formula
are required before **OK** becomes available.

Read the validation message below the formula when something is wrong. When
the editor can locate a formula error, it marks the relevant text with a red
wavy underline and gives the formula field a red border. Hover over the formula
field to see the error message as a tooltip.

A valid formula has passed syntax and column-type checks; this does not
guarantee that every calculated value is meaningful. Review the resulting
column after creating it.

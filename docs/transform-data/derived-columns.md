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

## Writing formulas {#writing-formulas}

Enter the expression directly in **f(x)**, without a leading `=`. This editor
uses its own formula language, not Excel formulas, Python or a complete SQL
expression language.

### Column references

Put column names in square brackets, including names containing spaces:

```text
[Unit price] * [Quantity]
```

Match the column name exactly, including its capitalization. Autocomplete
searches without regard to case, but inserts the actual column name for you.

If a column name contains a closing bracket, write that bracket twice.
For example, the column `Cost [net]` is referenced as `[Cost [net]]]`.
Autocomplete handles this escaping automatically.

### Numbers and text

Write numbers without quotes. Use a dot as the decimal separator and do not
include thousands separators: write `1250.50`, not `1,250.50` or `1250,50`.
Negative numbers such as `-5` and scientific notation such as `2.5e-3` are
also supported.

Put literal text in single quotes. Double an apostrophe inside the text:

| Expression | Text value |
|---|---|
| `'Standard'` | Standard |
| `'O''Brien'` | O'Brien |

A formula consisting only of a number or quoted text repeats that value in
every row. By contrast, `[Price]` reads a value from a column, and `'Price'`
is the literal word Price.

### Arithmetic

Arithmetic requires numeric values; text that looks like a number is not
automatically converted.

| Operator | Meaning | Example |
|---|---|---|
| `+` | Add | `[Price] + 5` |
| `-` | Subtract | `[Price] - 5` |
| `*` | Multiply | `[Price] * [Quantity]` |
| `/` | Divide | `[Price] / 2` |

Multiplication and division are evaluated before addition and subtraction.
Operators at the same level are evaluated from left to right. Use parentheses
to control the order:

| Formula | Result when Price is 10 |
|---|---|
| `[Price] + 2 * 3` | 16 |
| `([Price] + 2) * 3` | 36 |

## Conditional results with IF {#conditional-results-with-if}

Use `IF` to choose between two results for each row:

```text
IF(condition; then_result; else_result)
```

Separate the three arguments with **semicolons**, not commas. If the condition
is true, the formula returns `then_result`; otherwise it returns `else_result`.
A condition that is unknown because of a missing value also takes the else
branch.

### Assign a label

For a numeric **Quantity** column, this formula labels orders of three or more
items:

```text
IF([Quantity] >= 3; 'Bulk'; 'Standard')
```

| Quantity | Result |
|---|---|
| 1 | Standard |
| 3 | Bulk |
| 5 | Bulk |
| Missing | Standard |

`>=` means "greater than or equal to". The labels are quoted because they are
literal text, not column names.

### Choose between calculations

The results can also be calculations. For example, apply a 10% discount to the
line total when the quantity is at least three:

```text
IF([Quantity] >= 3; [Price] * [Quantity] * 0.9; [Price] * [Quantity])
```

| Price | Quantity | Result |
|---|---|---|
| 10 | 2 | 20 |
| 10 | 3 | 27 |

### Handle more than two outcomes

Put another `IF` inside a result branch to test a further condition. This
example checks the highest quantity first:

```text
IF([Quantity] >= 10; 'Large'; IF([Quantity] >= 3; 'Medium'; 'Small'))
```

| Quantity | Result |
|---|---|
| 2 | Small |
| 3 | Medium |
| 10 | Large |

The second condition is used only when the first condition is not true.

### Keep result types compatible

Both result branches must return numbers or both must return text. You can use
`NULL` (without quotes) in either kind of formula to produce a missing value.
For example:

```text
IF([Quantity] >= 3; 'Bulk'; NULL)
```

Do not mix text and numbers, such as `IF([Quantity] >= 3; 'Bulk'; 0)`.
Both branches are checked for compatible types even if your current data would
only use one of them.

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

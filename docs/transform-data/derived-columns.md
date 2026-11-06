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
4. In **f(x)**, enter `[Price] * [Quantity]`. The dialog confirms
   **Valid formula.**
5. Select **OK** to create the column.

![Derived column dialog with Column name set to Line total and f(x) set to
[Price] * [Quantity]](../assets/transform-data/derived_column.png){ width="420" }

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

## Condition reference {#condition-reference}

Conditions decide which result an `IF` returns. A condition alone, such as
`[Quantity] >= 3`, cannot be the final formula result. Wrap it in `IF` to
produce a label or number:

```text
IF([Quantity] >= 3; 1; 0)
```

### Comparisons

| Operator | Meaning | Example condition |
|---|---|---|
| `=` | Equal to | `[Quantity] = 3` |
| `!=` | Not equal to | `[Quantity] != 3` |
| `<` | Less than | `[Quantity] < 3` |
| `<=` | Less than or equal to | `[Quantity] <= 3` |
| `>` | Greater than | `[Quantity] > 3` |
| `>=` | Greater than or equal to | `[Quantity] >= 3` |

You can compare compatible columns or calculated values, not just a column
and a constant. For example, `[Price] * [Quantity] > [Budget]` compares a line
total with a budget from the same row.

Compare numbers with numbers and text with text. Use `[Quantity] = 3`, not
`[Quantity] = '3'`. For a text comparison, use a quoted value such as
`[Vehicle] = 'BMW'`.

### Ranges with BETWEEN

`BETWEEN` includes both endpoints:

```text
IF([Quantity] BETWEEN 3 AND 10; 'In range'; 'Outside range')
```

Quantities of 3 and 10 both return **In range**. Use
`[Quantity] NOT BETWEEN 3 AND 10` to test for values outside that range.
The `AND` between the bounds is part of the range syntax.

### Lists with IN

Use `IN` to match any value in a list:

```text
IF([Vehicle] IN('BMW', 'Volvo'); 'Selected'; 'Other')
```

Use **commas** between list values, while keeping **semicolons** between the
three `IF` arguments. `NOT IN` tests for values that do not match the list:

```text
IF([Vehicle] NOT IN('BMW', 'Volvo'); 'Other'; 'Selected')
```

List items must be literal values, not column references or calculations.
Keep their types compatible with the value being tested: for a numeric column,
use a list such as `[Quantity] IN(1, 3, 5)`.

### Combine conditions

| Keyword | Meaning | Example condition |
|---|---|---|
| `AND` | Both conditions must be true | `[Quantity] >= 3 AND [Price] < 20` |
| `OR` | At least one condition must be true | `[Quantity] >= 3 OR [Price] < 20` |
| `NOT` | Reverse a condition; unknown remains unknown | `NOT ([Quantity] >= 3)` |

For example, label a row only when both requirements are met:

```text
IF([Quantity] >= 3 AND [Price] < 20; 'Qualifies'; 'Other')
```

Comparisons and range/list tests are evaluated before `NOT`, then `AND`,
then `OR`. Use parentheses to make combined conditions clear:

```text
IF(([Vehicle] = 'BMW' OR [Vehicle] = 'Volvo') AND [Quantity] >= 3; 'Qualifies'; 'Other')
```

### Check for missing values

Use `IS NULL` or `IS NOT NULL`, not `= NULL` or `!= NULL`:

```text
IF([Vehicle] IS NULL; 'Missing'; [Vehicle])
```

An empty text value (`''`) is not a missing value. The formula above replaces
missing values but leaves empty text unchanged.

Ordinary comparisons with missing values produce an unknown condition.
Negating it with `NOT`, `NOT IN` or `NOT BETWEEN` does not make it true.
`IF` uses the else branch when its condition is unknown.

To explicitly include missing values alongside a comparison, combine a null
check with `OR`:

```text
IF([Vehicle] IS NULL OR [Vehicle] != 'BMW'; 'Other or missing'; 'BMW')
```

Do not put `NULL` in an `IN` list to match missing values; use `IS NULL`.
A list containing `NULL` can also make a nonmatching value's condition
unknown, which is particularly easy to overlook with `NOT IN`.

## Missing values and result types {#missing-values-and-result-types}

### Missing values in calculations

A missing input normally produces a missing arithmetic result. For example:

```text
[Price] * [Quantity]
```

| Price | Quantity | Result |
|---|---|---|
| 10 | 2 | 20 |
| Missing | 2 | Missing |
| 10 | Missing | Missing |

The word **Missing** in these tables describes an absent value; it is not text
to enter in the formula. Use the unquoted keyword `NULL` when you want a formula
to return a missing value.

### Replace missing values deliberately

Use `IF` with `IS NULL` to supply a replacement:

```text
IF([Quantity] IS NULL; 0; [Quantity])
```

This keeps existing quantities and substitutes zero only where the quantity is
missing. Only use zero if that interpretation makes sense for your data:
an unknown quantity is not necessarily a quantity of zero.

For a text column, use a text replacement instead:

```text
IF([Vehicle] IS NULL; 'Unknown'; [Vehicle])
```

This does not replace empty text (`''`). See
[Check for missing values](#check-for-missing-values) for null checks and
conditions involving missing values.

### Division by zero

Division by zero produces a missing result, not an infinite value:

```text
[Amount] / [Count]
```

| Amount | Count | Result |
|---|---|---|
| 10 | 2 | 5 |
| 10 | 0 | Missing |
| 10 | Missing | Missing |

Review missing results rather than assuming that a valid formula produces
a usable number in every row.

### The new column's type

The formula determines whether the new column contains numbers or text.
Numeric results use a nullable floating-point type, even when every result is
a whole number. Text results use a nullable text type. Both can hold missing
values.

Types are checked from the source columns, not guessed from a few sample
values. A text column containing values such as `'10'` is still text and cannot
be used directly in arithmetic. Convert the source column to a numeric type
before using it in a calculation.

For `IF`, keep both result branches compatible as described in
[Keep result types compatible](#keep-result-types-compatible).
There is no output-type selector in the Derived column dialog.

## Date and time functions {#date-and-time-functions}

Use these functions to extract a time of day or a calendar grouping from a
datetime column:

```text
YEARMONTH([When])
```

Replace **When** with your column name. The source must already have a datetime
type; text that looks like a date is not parsed automatically. Convert text
dates to a datetime type before using these functions.

### Function reference

The examples below use **2026-09-01 14:33:59** as the value in **When**.
Text outputs are shown without formula quotes.

| Formula | Result type | Example result |
|---|---|---|
| `TIME([When])` | Text | 14:33 |
| `WEEK([When])` | Text | W36 |
| `WEEK#([When])` | Number | 36 |
| `MONTH([When])` | Text | September |
| `MONTHSHORT([When])` | Text | Sep |
| `MONTH#([When])` | Number | 9 |
| `TERTIAL([When])` | Text | T3 |
| `TERTIAL#([When])` | Number | 3 |
| `QUARTER([When])` | Text | Q3 |
| `QUARTER#([When])` | Number | 3 |
| `YEAR([When])` | Number | 2026 |
| `ISOYEAR([When])` | Number | 2026 |
| `YEARWEEK([When])` | Text | 2026-W36 |
| `YEARMONTH([When])` | Text | 2026-09 |
| `YEARQUARTER([When])` | Text | 2026-Q3 |
| `YEARTERTIAL([When])` | Text | 2026-T3 |

`TIME` returns hours and minutes; seconds are omitted, not rounded.
`MONTH` and `MONTHSHORT` use month names in the application's selected
language. The table shows English names.

A quarter spans three months: Q1 is January–March, Q2 is April–June,
Q3 is July–September and Q4 is October–December.
A **tertial** spans four months: T1 is January–April, T2 is May–August
and T3 is September–December.

Use year-prefixed functions such as `YEARMONTH` when you need to distinguish
the same period in different years. `MONTH#`, for example, returns 9 for
September regardless of the year.

### Calendar year versus ISO week-year

`WEEK`, `WEEK#`, `ISOYEAR` and `YEARWEEK` use ISO weeks, which start on Monday.
ISO week 1 is the week containing January 4. Near New Year, a date can belong
to a different ISO week-year than its calendar year:

| When | `YEAR([When])` | `ISOYEAR([When])` | `YEARWEEK([When])` |
|---|---|---|---|
| 2019-12-30 | 2019 | 2020 | 2020-W01 |
| 2021-01-01 | 2021 | 2020 | 2020-W53 |
| 2021-01-04 | 2021 | 2021 | 2021-W01 |

Use `YEARWEEK` for a combined week label rather than pairing `YEAR` with
`WEEK#`, which can give the wrong year at these boundaries.

### Use extracted values in conditions

Numeric functions can be used in arithmetic and comparisons. This formula
labels dates in the first or second half of a year, while explicitly handling
missing dates:

```text
IF([When] IS NULL; 'Missing date'; IF(MONTH#([When]) <= 6; 'H1'; 'H2'))
```

| When | Result |
|---|---|
| 2026-01-01 | H1 |
| 2026-09-01 | H2 |
| Missing | Missing date |

### Missing dates and time zones

Each date/time function returns a missing value for a missing date.
Use `IS NULL` when you need a replacement label, as in the example above.

For timezone-aware columns, values are extracted in the column's stored time
zone without conversion. This matters for times near midnight, when converting
to another time zone could change the date, month or year.

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

## Troubleshooting {#troubleshooting}

Start with the validation message below **f(x)**. An error may simply mean
that you have not finished typing the expression.

| Problem | What to check |
|---|---|
| The new column name is rejected | Enter a unique, nonempty name without `[` or `]`. This dialog creates a new column; it does not overwrite an existing one. |
| A referenced column is not found | Match its name and capitalization exactly. Use autocomplete to insert the reference. |
| A column name is not unique | Rename duplicate source columns so each reference identifies one column. |
| A bracket, quote or parenthesis is unclosed | Check matching delimiters. Use single quotes for text and double an apostrophe inside a text value. |
| `IF` reports a separator or argument error | Use three arguments separated by semicolons. Use commas only between values in an `IN` list. |
| Operands or IF results have incompatible types | Do not mix text and numbers. Check the source column types, not just how their values look. |
| The formula returns a condition | Wrap the condition in `IF` to return text, a number or `NULL`. |
| A date/time function requires a datetime column | Convert text dates to a datetime type first. |
| Formula nesting is too deep | Simplify the expression or split the calculation across separate derived columns. |
| Creation fails despite successful validation | Check the actual source values as well as their column types. A column containing mixed kinds of values may pass initial checks but fail during calculation. |

For unexpected missing results, review
[Missing values and result types](#missing-values-and-result-types).
For unexpected labels, check the order of nested `IF` conditions and whether a
missing value is sending a row to the else branch.

For summaries and dataset-combination tasks, see
[Transform data](index.md).

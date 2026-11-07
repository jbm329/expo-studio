# Reshape

Use **Reshape** to summarize a dataset into groups and calculate named metrics
for each group. For example, create one row per region with total sales,
the number of recorded sales and sales for a selected product.

Reshape creates a **new result dataset** and leaves the source dataset unchanged.
This workflow groups and aggregates rows; it does not provide general
pivot/unpivot or wide-to-long controls.

In the Reshape dialog, select **Help** at the bottom left or press **F1** to
open this guide. **Preview**, **OK** and **Cancel** are grouped on the right.
Help leaves your dimensions, metrics and preview unchanged and does not
calculate or apply the configuration. If the browser cannot be opened, a
warning includes the manual URL.

## Create your first summary {#create-your-first-summary}

Start with this dataset. **Amount** must be a numeric column.

| Region | Product | Amount |
|---|---|---|
| North | A | 100 |
| North | B | 50 |
| South | A | 80 |
| South | A | 20 |
| South | B | Missing |

1. Select the result tab containing the source data and wait for it to finish
   loading.
2. Select **Reshape** on the toolbar.
3. Under **Dimensions**, check **Region**.
4. In the first **Metrics** row, select **SUM** and source column **Amount**.
   Set **Metric name** to `Total amount`. Leave **Condition (optional)** empty.
5. Select **Add metric**. Choose **COUNT**, source column **Amount**, and name
   the metric `Recorded amounts`.
6. Select **Preview**.

![Reshape dialog with Region as dimension, two metrics and a preview of North
and South totals](../assets/transform-data/reshape.png)

The preview shows:

| Region | Total amount | Recorded amounts |
|---|---|---|
| North | 150 | 2 |
| South | 100 | 2 |

**COUNT** counts nonmissing source values, so South has two recorded amounts,
not three.

Select **OK** to calculate the complete result in a new tab named
**Reshaped data**. **Cancel** closes the configuration without creating a result.
The dialog sometimes describes this action as "Apply"; its confirmation button
is **OK**.

The word **Missing** in this guide's tables represents an absent value, not
literal text to enter.

## Dimensions and output rows {#dimensions}

Dimensions define the grouping keys. Check one column for one row per distinct
value, or several columns for one row per distinct combination. For example,
checking **Region** and **Product** in the sample above creates four groups.

Leave all dimensions unchecked to calculate a single summary row for the
entire dataset.

Use **Search dimensions** to find columns by name. Searching only hides
nonmatching entries; it does not uncheck dimensions you have already selected.
Clear the search to review all selections.

Dimension columns appear first in their source-column order, followed by
metrics in their table order. Groups appear in the order they are first
encountered in the source, not alphabetically.

Missing dimension values are retained as grouping keys. Metric conditions
do not remove groups: a group remains in the output even if none of its rows
qualifies for a particular metric.

With an empty source, selected dimensions produce no output rows. Without
dimensions, the result still contains one summary row.

## Configure metrics {#metrics}

Each metric has a name, function, source column and optional row condition.
`FIRST` and `LAST` also require an ordering column.

Metric names must be nonempty and unique across **all output columns**,
including the selected dimensions. You can rename the automatically suggested
metric name.

Complete the current metric before selecting **Add metric**. To delete metrics,
select their rows and choose **Remove selected metrics**. At least one complete
metric is required.

### Function reference {#functions}

| Function | Meaning | Accepted source columns |
|---|---|---|
| `SUM` | Sum of nonmissing values | Integer or floating-point |
| `AVG` | Arithmetic mean of nonmissing values | Integer or floating-point |
| `MEDIAN` | Middle value; mean of the two middle values for an even count | Integer or floating-point |
| `COUNT` | Number of nonmissing values | Any column |
| `COUNT DISTINCT` | Number of distinct nonmissing values | Any column |
| `MIN` | Lowest number or earliest datetime | Numeric or datetime |
| `MAX` | Highest number or latest datetime | Numeric or datetime |
| `FIRST` | Source value from the row with the lowest/earliest ordering value | Any value column; numeric or datetime ordering |
| `LAST` | Source value from the row with the highest/latest ordering value | Any value column; numeric or datetime ordering |

The source dropdown only offers columns compatible with the selected function.
Changing the function clears the source selection if it is no longer compatible.
Text containing numbers is not a numeric type, and Boolean columns are not
offered for numeric aggregations. Convert source types before opening Reshape
when necessary.

Selecting a column does not guarantee every operation can process its contents:
complex or mixed values can still cause calculation errors, particularly for
distinct counting or conditions.

### Missing values and empty matches

`SUM`, `AVG`, `MEDIAN`, `MIN` and `MAX` ignore missing source values. If a
group has no qualifying nonmissing values, these metrics return a missing
value, **including SUM**; they do not substitute zero.

`COUNT` and `COUNT DISTINCT` exclude missing values and return zero when
there are no qualifying nonmissing values. Empty text (`''`) is a value,
not a missing value, and is included in counts.

To count rows, choose a source column that is populated in every row.
There is no `COUNT(*)` option. To count rows with a missing **Amount**, for
example, use a fully populated identifier as the COUNT source and
`[Amount] IS NULL` as its condition.

### FIRST and LAST {#first-and-last}

These functions select an actual row's value rather than calculating the
minimum or maximum of the value column.

1. Choose **FIRST** or **LAST**.
2. Select the **Source column** whose value you want returned.
3. In the adjacent **Order by** selector, choose a numeric or datetime column.
4. Optionally add a condition to limit the eligible rows.

For example, select **Status** as the source and **Recorded at** as the
ordering column:

| Account | Recorded at | Status |
|---|---|---|
| A | 2026-01-03 | Closed |
| A | 2026-01-01 | Open |
| A | 2026-01-03 | Reopened |

With **Account** as the dimension, `FIRST` returns **Open** and `LAST`
returns **Reopened**. **Recorded at** must have a datetime type.

Conditions filter rows **before ordering**. Missing ordering values are
excluded. For equal ordering values, FIRST chooses the earliest source row
and LAST chooses the latest source row. This tie-break uses source row order,
not the value column's contents.

A missing value in the selected row is kept; FIRST/LAST do not skip it to find
a nonmissing value. Add a condition such as `[Status] IS NOT NULL` if that is
what you need. A group with no eligible ordering values returns a missing result.

## Conditional metrics {#metric-conditions}

A condition filters the source rows used by **one metric only**. It does not
filter other metrics or remove dimension groups. Leave it empty to include
all rows for that metric.

To add product A sales alongside the totals from the first example, add:

| Metric name | Function | Source column | Condition |
|---|---|---|---|
| Product A amount | SUM | Amount | `[Product] = 'A'` |

![Reshape dialog with a third metric whose condition editor contains
[Product] = 'A'](../assets/transform-data/reshape_metric_condition_editor.png)

The result becomes:

| Region | Total amount | Recorded amounts | Product A amount |
|---|---|---|---|
| North | 150 | 2 | 100 |
| South | 100 | 2 | 100 |

Conditions use source columns, not names of other output metrics. They are
applied before aggregation, not to the aggregated total.

### Build a condition visually {#condition-builder}

In **Build condition**, select **Help** at the bottom left or press **F1** to
open this section. **Apply** and **Cancel** remain on the right. Help preserves
your rules, groups and selected values without applying the condition.
If the browser cannot be opened, a warning includes the manual URL.

1. Complete the metric name, function and source selection.
2. Select the **...** button beside its condition field to open
   **Build condition**.
3. Select a column and an operator, such as **Product** and **Equal to**.
4. Open **Select values**, then check the desired value.
5. Select **Apply** to put the generated condition into that metric.

![Build condition dialog with one rule: Product, Equal to, one value
selected](../assets/transform-data/reshape_metric_condition_builder.png){ width="600" }

The builder's **Apply** button only updates the condition. It does not run
Reshape. **Cancel** leaves the metric's existing condition unchanged.

Use **Search values**, **Previous** and **Next** to find values. Selections
are retained across searches and pages. Review **Selected values** and use
**Remove selected values** to remove unwanted selections.

**In** and **Not in** allow multiple values. Other comparison operators require
one value. **Is missing** and **Is not missing** need no value selection;
missing values are not ordinary choices in the value list. Empty text is
shown as **(empty string)**.

The builder selects existing source values. To use a new literal threshold,
such as an amount not present in the dataset, enter it manually in the
condition field.

### Combine rules and groups

Use **Add rule** to add another rule. Choose **All rules (AND)** when every
rule must match, or **Any rule (OR)** when at least one must match.
Each group has its own connector.

For example, this condition selects product A or B, but only for positive amounts:

```text
([Product] = 'A' OR [Product] = 'B') AND [Amount] > 0
```

In the builder, make an OR group containing the two product rules and combine
it with the amount rule using AND at the outer level.

Drag a row's **::** handle onto another rule to create an AND group. Drop onto
a group to add to it, or use row edges to reorder. Change the new group's
connector to OR if needed.

Click the handle for actions such as **Move up**, **Move down**,
**Group with previous (AND)**, **Move out of group** and
**Ungroup (use parent operator)**. Ungrouping adopts the parent's connector,
so review the logic afterward. Use **Remove rule** to delete a rule.

You can reopen the builder after editing text manually. Valid, representable
text is imported with its grouping; invalid or ambiguous text must be corrected
before the builder can open. Applying the builder writes its generated text
back to the field, so formatting may change.

## Write conditions manually {#condition-syntax}

Click or focus a condition field to open its larger multiline editor.
Type the condition directly, without a leading `=` and without wrapping it
in `IF`.

### Column names and literal values

Use square brackets around source column names. Match their spelling and
capitalization exactly. A closing bracket inside a name is escaped as `]]`,
as in [Derived column references](derived-columns.md#column-references).

Literal syntax depends on the source column's type:

| Column type | Example condition | Value syntax |
|---|---|---|
| Integer or floating-point | `[Amount] >= 100.5` | Unquoted number, decimal dot, no thousands separators |
| Boolean | `[Approved] = True` | Unquoted `True` or `False` |
| Text | `[Product] = 'A'` | Single-quoted text |
| Datetime | `[Recorded at] >= '2026-01-01'` | Single-quoted datetime value |

Double an apostrophe in quoted text: `[Customer] = 'O''Brien'`.
For an empty string, use `[Product] = ''`.
Negative numbers and scientific notation, such as `-5` and `2.5e-3`, are
supported for numeric columns.

Other source types, including categorical and object columns, use quoted
condition values. Use the builder to select their existing values rather than
assuming that a numeric-looking label accepts an unquoted number.

For datetime comparisons, a date such as `'2026-01-01'` represents midnight,
not the entire day. To select a full day, use an inclusive start and exclusive
next-day bound:

```text
[Recorded at] >= '2026-01-01' AND [Recorded at] < '2026-01-02'
```

For timezone-aware columns, a datetime without an offset is interpreted in the
column's stored time zone. An explicit offset is converted to that time zone.
Do not compare an offset-bearing literal with a timezone-naive column.
Ambiguous or nonexistent local times around daylight-saving changes can fail
during calculation; use an explicit offset when needed.

### Supported operators

| Operator | Meaning | Example |
|---|---|---|
| `=` | Equal to | `[Product] = 'A'` |
| `!=` | Not equal to | `[Product] != 'A'` |
| `>` | Greater than | `[Amount] > 100` |
| `>=` | Greater than or equal to | `[Amount] >= 100` |
| `<` | Less than | `[Amount] < 100` |
| `<=` | Less than or equal to | `[Amount] <= 100` |
| `IN` | Matches any listed value | `[Product] IN('A', 'B')` |
| `NOT IN` | Matches none of the listed values | `[Product] NOT IN('A', 'B')` |
| `IS NULL` | Is missing | `[Amount] IS NULL` |
| `IS NOT NULL` | Is not missing | `[Amount] IS NOT NULL` |

`IN` and `NOT IN` require a nonempty, comma-separated list in parentheses.
Each item uses the appropriate literal syntax for the tested column.
Comparisons must be meaningful for the column's actual values and type.

Combine conditions with `AND` and `OR`. AND takes precedence over OR;
parentheses override that order. Keywords are not case-sensitive.

### Missing values in conditions

Use `IS NULL` and `IS NOT NULL`, not `= NULL` or `!= NULL`.
`NULL` is not a value you can put in an `IN` list.

Ordinary comparisons, including `!=` and `NOT IN`, exclude rows where the
tested value is missing. To include those rows explicitly, add a null check:

```text
[Product] != 'A' OR [Product] IS NULL
```

Empty text and missing values are different. `[Product] = ''` matches empty
text; `[Product] IS NULL` matches missing values.

### Differences from Derived column formulas

Reshape conditions are row filters, not calculated-result formulas.
They do **not** support `IF`, arithmetic expressions, date-extraction functions,
standalone `NOT`, `BETWEEN`, or comparisons between two columns.

For an inclusive numeric range, write:

```text
[Amount] >= 100 AND [Amount] <= 500
```

If you need to filter a calculated value, create a
[derived column](derived-columns.md) first, then open Reshape on that dataset
and reference the new column.

## Editor assistance {#editor-assistance}

In the expanded condition editor, type `[` to see available column names.
Continue typing to narrow the suggestions without regard to case. Choose with
the mouse, or use arrow keys and **Enter** or **Tab** to accept. Brackets and
escaped closing brackets are inserted automatically. Suggestions complete
column names, not values or functions.

**Esc** dismisses suggestions first. With suggestions closed, **Esc** closes
the expanded editor without undoing your edits. Clicking outside also closes
it and keeps the text.

Syntax and column references are checked as you type. Errors give the field
a red border and mark the relevant text with a red wavy underline in the
expanded editor. Hover for an explanation. Invalid conditions prevent
**Preview** and **OK**.

These checks do not evaluate values. A syntactically valid datetime literal,
for example, can still fail when interpreted during Preview. Always review
the calculated output.

## Preview and create the result {#preview-and-create}

**Preview** calculates against the **full source dataset**, then displays up
to five output rows and the total output row count. It does not aggregate just
five input rows, so a large dataset can take time even for a short preview.

Changing dimensions, metrics or conditions makes a previous preview out of
date. Select **Preview** again to recalculate. Configuration remains editable
during preview calculation, but Preview and OK are unavailable while it runs.

Preview is recommended but not required. Once the configuration is complete
and conditions are valid, **OK** calculates every output row in a new result
tab. It is not limited to the five-row preview. The source remains unchanged.
Closing a pending result tab cancels its job; cancelled or failed calculations
do not leave a completed result dataset.

## Recipes {#recipes}

### Compare subsets side by side

Reuse the same source column in several metrics with different conditions.
For example, group by **Region** and add two SUM metrics over **Amount**:
one with `[Product] = 'A'` and one with `[Product] = 'B'`.

For the first example's data:

| Region | Product A amount | Product B amount |
|---|---|---|
| North | 100 | 50 |
| South | 100 | Missing |

South's product B amount is missing because its only matching amount is
missing. It is not zero.

### Group dates by month

First create a derived column named **Month** with `YEARMONTH([Recorded at])`.
Then open Reshape on that dataset, select **Month** as a dimension and add
the desired metrics. The year-prefixed label keeps January in different years
separate.

### Count distinct customers

Select **COUNT DISTINCT** with **Customer** as its source and name it
**Unique customers**. Choose dimensions for the desired breakdown, or none
for one overall count. Repeated nonmissing customer values count once per group;
missing values do not count.

## Troubleshooting {#troubleshooting}

| Problem | What to check |
|---|---|
| Reshape is unavailable | Select a ready result dataset and wait for loading to finish. |
| A dimension seems missing | Clear **Search dimensions**. Hidden checked dimensions still participate in grouping. |
| A source column is absent from the dropdown | Check the selected function's type requirements. Convert text numbers or dates before reshaping. |
| Add metric is disabled | Complete existing metric names and sources, including ordering for FIRST/LAST. |
| Preview or OK is disabled | Complete every metric, correct condition errors, select required ordering columns, and make output names unique. Wait for any running preview to finish. |
| The builder button is disabled | Complete that metric's name and source selection. |
| A condition column is ambiguous | Rename duplicate source columns before writing or building conditions. |
| The builder cannot load or distinguish values | Check for unsupported complex values or mixed values with identical text. Convert the column to an unambiguous scalar type. |
| A condition passes lint but calculation fails | Check literal contents and actual source values. Syntax checking does not validate datetime parsing or every comparison. |
| COUNT is lower than the number of rows | COUNT excludes missing source values. Use a fully populated source column to count rows. |
| A group remains despite no condition matches | Conditions apply independently to metrics, not to the dimension groups. Counts return zero; other aggregations return missing. |
| FIRST/LAST returns a missing value | Check missing ordering values, the metric condition and whether the selected row's value is itself missing. |
| Preview shows only five rows | This is the display limit. Check its total row count; OK creates the complete result. |
| Preview is out of date | Select Preview again after configuration changes. |

For calculated columns or combining datasets, see
[Transform data](index.md).

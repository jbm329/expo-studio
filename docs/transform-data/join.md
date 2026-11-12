# Join datasets

Use **Join datasets** to combine columns from two datasets by matching values
in a key column. Choose a join when each row in one dataset should be paired
with matching information from another, such as adding customer details to
orders. To append rows from datasets with the same kind of records, use
[Concatenate datasets](concatenate.md) instead.

A join creates a new result dataset and leaves both input datasets unchanged.
This is a code-free workbench operation, separate from writing a SQL `JOIN`:
select any two datasets that are open as result tabs. They can come from
different sources, such as local files, REST API results, or queries run
through different database connections.

In the Join datasets dialog, select **Help** at the bottom left or press **F1**
to open this guide. **Preview**, **OK** and **Cancel** are grouped on the right.
Help leaves your selections unchanged and does not preview or run the join.
If the browser cannot be opened, a warning includes the manual URL.

## Create your first join {#create-your-first-join}

Suppose the first dataset contains orders:

| Order ID | Customer ID | Amount |
|---|---|---:|
| 101 | C1 | 25 |
| 102 | C2 | 40 |
| 103 | C4 | 15 |

The second dataset contains customer details:

| ID | Customer | Region |
|---|---|---|
| C1 | Maya | North |
| C2 | Leo | South |
| C3 | Ava | West |

To add customer details to matching orders:

1. Select the result tab for the orders dataset.
2. Select **Join datasets** on the toolbar. You can also right-click a result
   tab and select **Join…**.
3. In **Left dataset**, choose the orders dataset. In **Right dataset**, choose
   the customer dataset.
4. Choose **Customer ID** as the left **Key** and **ID** as the right **Key**.
   The dialog may select compatible keys automatically.
5. In **Columns to include**, keep the columns you want from each dataset.
   Join keys are kept in the result even if you uncheck them.
6. Select **Inner join**, then select **Preview** to inspect the match.

![Join dialog with Orders and Customers selected, Customer ID and ID as keys,
and Inner join selected](../assets/transform-data/join.png)

With dataset tabs named **Orders** and **Customers**, the preview contains
rows for keys present in both datasets:

| join_status (Orders INNER Customers) | Order ID | Customer ID | Amount | ID | Customer | Region |
|---|---:|---|---:|---|---|---|
| both | 101 | C1 | 25 | C1 | Maya | North |
| both | 102 | C2 | 40 | C2 | Leo | South |

The order with customer `C4` and the customer `C3` are not included in an
inner join because neither has a matching row on the other side.

Select **OK** to create the full joined result in a new tab named
**Joined data**. **Cancel** closes the dialog without creating a result.

## Choose a join type {#join-types}

The join type determines what happens to rows without a matching key:

| Join type | Rows kept |
|---|---|
| **Inner join** | Only rows with a matching key in both datasets. |
| **Left join** | Every row from the left dataset, with matching right-side values where available. |
| **Right join** | Every row from the right dataset, with matching left-side values where available. |
| **Full (outer) join** | Every row from both datasets. Unmatched rows have missing values for the other side. |

In the example, a **Left join** keeps order `103` with missing customer
details. A **Full (outer) join** also keeps customer `C3` with missing order
details.

With the default **NULL** setting, included integer and boolean columns on the
side that can be missing use nullable types: right-side columns for a left
join, left-side columns for a right join, and both sides for a full join.
For example, `int64` becomes `Int64` and `bool` becomes `boolean`, even when every
row matches. This preserves integer precision without converting integers to
floating-point values. Integer widths and signedness are preserved, and existing
nullable types remain unchanged. Non-NULL defaults can retain the original
non-nullable type, as described below. Inner joins do not apply this conversion.
Neither input dataset is modified.

## Set defaults for unmatched rows {#unmatched-defaults}

The **If no match** column controls values for rows where that column's source
dataset has no matching row. Click a cell to open its value picker, or select the cell
and press **Enter**, **Space** or **F2**. **NULL** is the default.
Choose a preset under **Default:**, or select **Custom value...** and enter a
value under **Value:**. Confirm with **OK** to save the default; **Cancel**
leaves the cell unchanged. To enter text, type the text itself without wrapping
it in quotes. The table displays quotes to distinguish text from NULL.

| Source type | Available defaults |
|---|---|
| Integer | NULL, 0 or a custom integer within the column's range. |
| Float | NULL, 0.0 or a custom finite number within the column's range. |
| Boolean | NULL, True or False. |
| String, text-like object or category | NULL or custom text, including empty text. |
| Datetime | NULL or a custom date/time. |
| Timedelta, period or unsupported type | NULL only. |

Defaults are enabled for included non-key columns on the missing side:
right-side columns for a left join, left-side columns for a right join, and both
sides for a full join. Inner joins have no unmatched rows. Changing join type,
key or column inclusion temporarily disables inapplicable defaults; their
values are retained if you re-enable them. Changing datasets resets defaults.

Defaults replace only values introduced because a source row is absent.
Existing NULLs in matched rows are unchanged. For example, in the orders and
customers example, use a left join and set the right-side **Region** default to
`Unknown`. Order `103` then has `Unknown` as its region; a matched customer
whose region was already NULL still has NULL. The generated join status is
unchanged by defaults:

| Order ID | Customer ID | Region | join_status (Orders LEFT Customers) |
|---|---|---|---|
| 101 | C1 | North | both |
| 102 | C2 | South | both |
| 103 | C4 | Unknown | left_only |

Use the same approach to set a custom integer, such as `0` for an unmatched
quantity. Choose a default only when it has the intended meaning: zero means
a known zero quantity, whereas NULL means no value is available.

Use **Numeric columns** or **Text columns** and **Set defaults...** to set
defaults for all eligible columns of that type on one side. The value must be
valid for every applicable column; otherwise no defaults are changed.
Choose **NULL** in the picker to reset the applicable defaults.

Custom numbers use the system numeric locale, independently of UI language.
Enter numbers without grouping separators. Integer input accepts whole numbers,
not decimals or scientific notation. Float input also accepts scientific notation.
Text whitespace is preserved. A new categorical text default is added to the
categories without changing existing category values or ordering.
Object columns must contain only text or missing values to accept a text default;
the join worker checks their contents and reports incompatible values.

For datetimes, use the date/time picker or enter an ISO date/time. The picker
uses the column's local wall time; explicit offsets in typed input identify an
instant and are converted to the column's timezone. For timezone-naive columns,
enter a value without an offset. Ambiguous or nonexistent local times, invalid
dates, out-of-range values and precision finer than the column's resolution are
rejected rather than silently adjusted.

Integer and boolean source columns with a non-NULL default retain their
original NumPy type after filling. Existing nullable source types and NULLs
remain nullable. Preview and the final join use the same defaults.

## Performance and exporting {#performance-and-exporting}

Nullable integer and boolean columns store a missing-value mask, adding about
one byte per row to that column's value storage. For example, `int64` uses
8 bytes per value and nullable `Int64` uses about 9 bytes including its mask.
This is not a percentage increase for the whole dataset. Nullable booleans can
use less memory than the object columns otherwise produced by unmatched joins.

Preparing nullable columns and applying non-NULL defaults adds processing and
temporary memory use. The cost depends on row count, selected columns and join
shape; it is not guaranteed to be negligible, even when every row matches.
Each custom default adds column-level work. **Preview** performs the join
before selecting up to 100 rows, so it is not a low-cost substitute for a full
join on a large dataset.

Parquet, Feather and the app's pickle dataset format preserve nullable types,
missing values and full-width integer values. CSV stores text rather than a
dtype schema: exported integers retain their digits, but the application reading
the CSV must interpret them as integers without first converting them to floats.
Excel preserves blank cells and boolean values, but its numeric precision limit
still applies to large integers. Use Parquet or Feather when exact large integer
identifiers and nullable types must survive export and reloading.

## Select keys and output columns {#keys-and-columns}

Choose one key column from each dataset. The values to match must have
compatible data types; the dialog enables compatible right-side keys for the
selected left key. Column names do not need to be the same. For example,
**Customer ID** can match **ID**.

The key suggestions are a convenience, not a check that values have the
meaning you intend. Confirm that the selected columns identify the same kind
of entity in both datasets. A key may appear more than once, which can create
more than one output row for a match.

Use the checkboxes in the **Columns to include** table to choose non-key columns
for the result. The **Type** column shows each source column's data type.
Resize the dialog to give the tables more room. The selected key columns and
the current join's generated status column are retained automatically.
The status identifies whether a row matched both datasets
(`both`), only the left (`left_only`), or only the right (`right_only`).

The status column is placed first and is named
`join_status (<left dataset> <JOIN TYPE> <right dataset>)`, using the dataset
tab names and `INNER`, `LEFT`, `RIGHT`, or `FULL OUTER`. For example:
`join_status (Film LEFT Actor)`. These type labels remain English regardless
of the interface language. Renaming a tab later does not rename existing
status columns.

If that name is already present in either input or the merged output, the new
column receives the first available numbered suffix, starting with
`join_status (Film LEFT Actor) 2`. Existing columns are never replaced by the
new status. You can join an earlier join result again: historical status
columns, including columns named simply `join_status`, follow the ordinary
**Columns to include** selections. Only the newly generated status column is
retained automatically. Historical status columns can also be selected as keys.

Exports use the same descriptive headers. When referencing them in SQL, quote
the complete identifier, for example `"join_status (Film LEFT Actor)"`.

When both datasets contain a selected non-key column with the same name, the
result distinguishes them with suffixes based on the dataset tab names.
Rename columns before joining if those suffixes would be unclear.

## Preview and check matches {#preview}

Select **Preview** to review sample result rows and join metadata before
creating the result:

In the preview dialog, select **Help** at the bottom left or press **F1** to
open this section. **Close** stays on the right. Help leaves the preview and
join configuration unchanged.

![Join preview showing sample rows, match percentages, cardinality, and the
estimated number of rows](../assets/transform-data/join_preview.png)

The preview shows up to 100 rows from the joined result. **Match success**,
**Left only**, and **Right only** describe the proportions in that sample,
not necessarily the complete result. **Cardinality** describes whether the
selected key is unique on either side. **Estimated number of rows** is an
estimate; compare it with the result after creating the join.
Percentages and status-cell highlighting refer to the current join, not to
historical status columns retained from earlier joins. Left-only status cells
are highlighted yellow and right-only status cells red.

Repeated keys can multiply output rows. If a key occurs several times in both
datasets, every matching left row is paired with every matching right row for
that key. Check key uniqueness and the estimated size before confirming,
especially when the preview reports many-to-many cardinality.

## Troubleshooting {#troubleshooting}

| Problem | What to check |
|---|---|
| The right key cannot be selected | Choose a right-side column with a compatible data type, or convert the key columns before joining. |
| The preview has few or no matches | Check that the selected columns represent the same identifier and that their values have compatible types and matching content. |
| The result has more rows than either input | Check for repeated keys. Duplicate key values can produce multiple matching pairs. |
| Values are missing after a join | An outer, left, or right join retains unmatched rows; inspect the first, generated status column to see which side had no match. |
| An **If no match** cell is disabled | Choose a join type that can leave that side unmatched, include the column, and check that it is not a join key. |
| A custom default is rejected | Check the source type, numeric range, locale decimal separator, and datetime timezone or resolution. Mixed non-text object columns accept NULL only. |
| A matched row still contains NULL after setting a default | Defaults apply only when the source row is absent; they do not replace NULLs already present in matching source rows. |
| A column name has a dataset suffix | Both datasets contain a selected column with that name. Rename the source columns or use the suffix to distinguish them. |
| A status column name ends in a number | Its descriptive base name was already occupied. The new status uses a numbered name to preserve existing columns. |
| The preview estimate differs from the final row count | The preview row sample and estimated row count are not a complete calculation. Review the created result and its current join status values. |

For calculated columns, summaries or appending rows, see
[Transform data](index.md).

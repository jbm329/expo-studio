# Concatenate datasets

Use **Concatenate datasets** to append the rows from one dataset to another.
This is useful when two datasets contain the same kind of records, such as
tracks from different playlists or sales from different periods. Columns are
aligned by name, not position. To add matching information as new columns,
use a [join](join.md) instead.

Concatenate is a code-free workbench operation. It combines two datasets that
are open as result tabs, even when they came from different sources.

In the Concatenate datasets dialog, select **Help** at the bottom left or
press **F1** to open this guide. **OK** and **Cancel** remain on the right.
Help leaves your dataset selections unchanged and does not run concatenation.
If the browser cannot be opened, a warning includes the manual URL.

## Append one dataset to another {#append-datasets}

Suppose one dataset contains rock tracks and another contains jazz tracks:

**Rock tracks**

| Artist | Track | Album |
|---|---|---|
| Nina Simone | Sinnerman | Pastel Blues |
| The Kinks | Waterloo Sunset | Something Else |

**Jazz tracks**

| Artist | Track | Label |
|---|---|---|
| Miles Davis | So What | Columbia |
| Nina Simone | My Baby Just Cares for Me | Bethlehem |

To append the jazz rows to the rock dataset:

1. Select the result tab for the dataset you want first in the output.
2. Select **Concatenate datasets** on the toolbar. You can also right-click a
   result tab and select **Concatenate…**.
3. In **Second dataset**, choose the dataset to append. The first dataset is
   the active result tab; its columns and the second dataset's columns are
   shown in **Column** / **Type** / **If absent** tables.
   Resize the dialog to give them more room.
4. Leave all columns checked, or uncheck columns you do not want that dataset
   to supply. Each panel's **Select all** checks every column; selecting it again
   clears the panel. A partially checked Select all means some columns are
   included; selecting it includes all of them. These controls are below each
   column table.
5. For a selected column that is included on only one side, optionally choose
   a default in **If absent**. It applies to rows from the other dataset only.
   Below the table, you can also use **Numeric columns** or **Text columns**
   and **Set defaults…** to apply one value to all eligible columns of that type.
6. Select **OK** to create the concatenated result. At least one column must
   remain checked across the two panels.

![Concatenate datasets dialog showing column inclusion checkboxes, types,
If absent defaults, and controls below each column table](../assets/transform-data/concatenate.png)

The result is a new tab named **Concatenated data**. The first dataset's rows
come first, followed by the second dataset's rows:

| Artist | Track | Album | Label |
|---|---|---|---|
| Nina Simone | Sinnerman | Pastel Blues | Missing |
| The Kinks | Waterloo Sunset | Something Else | Missing |
| Miles Davis | So What | Missing | Columbia |
| Nina Simone | My Baby Just Cares for Me | Missing | Bethlehem |

Columns with the same name are combined, even if they appear in different
positions in the inputs. A column found in only one dataset is still included;
rows from the other dataset have missing values in that column. Different
column names remain separate even if they contain similar information.

The word **Missing** in this guide's table represents an absent value, not
literal text.

## Choose included columns {#included-columns}

All columns start checked. A column appears in the output if it is checked in
either dataset. Output columns follow the first dataset's source order, followed
by columns included only from the second dataset in its source order.

Unchecking a column excludes that dataset's values, **not its rows**. If the
same column is checked in the other dataset, the excluded side's rows contain
missing values for that column. Existing NULLs in included source columns are
unchanged. You can clear every column on one side while retaining its rows,
provided at least one column is checked on the other side.

For example, unchecking **Artist** only in Jazz tracks retains both jazz rows,
but their Artist cells are missing; the rock rows still contain their artists.
Unchecking Artist in both panels removes Artist from the output.

Choosing a different **Second dataset** checks all its columns again and keeps
your first-dataset selections. Help does not reset selections.

Column selection requires unique column names within each dataset. If a
dataset has duplicate names, its columns remain included and its inclusion
controls are unavailable. Rename duplicate columns before choosing a subset.

## Column types and missing values {#column-types}

When a column is included from only one dataset, integer and boolean columns use
nullable types so the other dataset's rows can contain missing values.
For example, `int64` becomes `Int64`, `uint64` becomes `UInt64`, and `bool`
becomes `boolean`. Integer widths and signedness are preserved, avoiding
floating-point conversion and rounding of large integer values.
This schema-based rule also applies when the dataset lacking the column has
no rows. A non-NULL default allows a one-sided NumPy integer or boolean column
to retain its original type instead. Existing nullable types and source NULLs
remain unchanged.

For columns included from both datasets, the inputs' types are reconciled by
pandas as before. This is separate from filling an absent column: combining
integers with floats, or incompatible signed and unsigned integers, can still
produce floats and lose precision. Check and intentionally convert shared
columns to compatible types before concatenating when exact values matter.

### Set defaults for absent columns {#absent-column-defaults}

The **If absent** cell is enabled for supported types only when the column is
checked in one panel and not checked in the other. Unavailable cells are
disabled and dimmed. A default fills generated
values for the other dataset's rows; it never replaces NULLs already present
in the column's source rows. A checked column in both panels has no default.
Unchecking it on one side makes it absent there, so the selected side's default
applies to those rows.

Choose a cell to open its type-aware editor:

| Column type | Available values |
|---|---|
| Integer | NULL, 0, or a custom integer within the column's range |
| Float | NULL, 0.0, or a custom finite number within the column's range |
| Boolean | NULL, True or False |
| String, text-only object or category | NULL or custom text, including empty text |
| Datetime | NULL or a custom date/time that preserves the column's timezone and precision |
| Other types, such as period or timedelta | NULL only |

Custom numbers use the app's decimal separator and do not accept grouping
separators. For datetime columns without a timezone, enter a date/time without
an offset. For timezone-aware columns, a value without an offset is interpreted
in the column's timezone; an explicit offset is converted to that timezone.
Ambiguous or nonexistent local times are rejected; an explicit offset can
disambiguate a repeated local time. Values must fit the column's range and
resolution without rounding. For object
columns, text-only source values are checked when concatenation runs, not while
the dialog is open. Custom category text can add a new category.

Each panel's **Numeric columns** or **Text columns** menu with **Set defaults…**
sets a shared value for eligible numeric or text columns. The app validates the
value for every target before changing any defaults. If a value does not fit
all target types or ranges, none are changed. Boolean, datetime and
NULL-only types are configured per column where supported.

Changing the second dataset resets defaults in both panels to NULL, while
retaining first-dataset column selections. Defaults are settings for the
current dataset pair only.

Different column layouts require unique column names. Rename duplicate
columns before concatenating datasets with different layouts.

### Example: default only the absent rows {#absent-default-example}

Suppose the first dataset has an `Int64` **Quantity** column containing `5`
and an existing NULL. The second dataset has two rows but no Quantity column.
Leave Quantity checked in the first panel and set its **If absent** value to
`0`. The output Quantity values are:

| Source row | Quantity |
|---|---|
| First dataset, row 1 | 5 |
| First dataset, row 2 | NULL |
| Second dataset, row 1 | 0 |
| Second dataset, row 2 | 0 |

Quantity remains `Int64`. Leaving the default as NULL would instead produce
`5`, NULL, NULL, NULL. If the second dataset does have Quantity but you uncheck
it there, its source values are excluded and the first panel's default applies
to those rows in exactly the same way.

## Performance, memory and exports {#performance-and-exports}

Concatenation runs in the background, but constructing the combined dataset
still takes time and memory. Nullable preparation and typed absent segments
add work, especially with many one-sided columns. Identical column layouts
without defaults retain the existing pandas concatenation path.

A nullable integer's missing-value mask adds about one byte per output value:
`int64` uses 8 bytes per value, while `Int64` uses about 9 bytes including its
mask. This is not a percentage increase for the whole dataset. Nullable
booleans can use less memory than pandas' object-promoted absent columns.
Non-NULL defaults can retain NumPy integer/boolean storage, but validating and
constructing defaults also costs processing and temporary memory.

In one local diagnostic with two one-million-row inputs, two integer columns
per input and one shared column, pandas concatenation took about 15 ms,
nullable NULL handling 34 ms, and numeric defaults 16 ms. Retained output memory
was about 46, 50 and 46 MiB respectively. Wider disjoint integer schemas had
larger preparation costs. These measurements exclude input creation and are
illustrative, not performance guarantees or measurements of peak memory.

Parquet, Feather and the app's pickle dataset format preserve nullable types,
missing values and full-width integer values. CSV stores text, not a dtype
schema: exported integers retain their digits, but the application reading
the CSV must interpret them without first converting them to floats.
Normal and streaming Excel export preserve blank cells and boolean values,
but Excel's numeric precision limit still applies to large integers. Use
Parquet or Feather when exact large integer identifiers and nullable types
must survive export and reloading.

## What Concatenate does {#concatenate-behavior}

- Every row from both datasets is retained, including duplicate rows.
- Rows from the first dataset precede rows from the second dataset.
- Columns are matched by name; the dialog does not let you map, rename or
  reorder columns.
- The dialog does not provide a preview or an option to remove duplicates.
- The input datasets are unchanged. The combined data is created in a new
  result tab.

## Troubleshooting {#troubleshooting}

| Problem | What to check |
|---|---|
| Concatenate does not open | Keep at least two result datasets open. The active dataset is the first; another open dataset is required as the second. |
| Concatenate reports that an output column is required | At least one input dataset must contain a column. Inputs with no rows are supported when an input still defines columns. |
| Values appear under separate columns | Column names must match exactly to be combined. Rename columns before concatenating if they represent the same information. |
| Some output cells are missing | One input dataset does not have a column with that name. This is expected when the inputs have different columns. |
| Values disappeared after unchecking a shared column | Unchecking excludes that dataset's values. Check the column in both panels to retain both datasets' values. |
| OK is unavailable | Check at least one column in either panel. You can leave the other panel empty without dropping its rows. |
| An **If absent** cell is disabled | Include the column on only one side and check that its type supports defaults. Shared selected columns and unsupported types have no editable default. |
| A custom default is rejected | Check the numeric range, decimal separator, and datetime timezone or resolution. A non-NULL object default requires text-only source values. |
| A source NULL remains after setting a default | Defaults fill absent-column segments only; existing NULLs in included source columns are unchanged. |
| Duplicate rows remain | Concatenate preserves all input rows. Remove duplicates in a separate preparation step if needed. |
| Rows appear in an unexpected order | The active dataset is first, and its rows precede the rows from the selected second dataset. |

For calculated columns, summaries or matching records, see
[Transform data](index.md).

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
   shown for reference in read-only **Column** / **Type** tables. Resize the
   dialog to give the tables more room; all columns remain included.
4. Select **OK** to create the concatenated result.

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

## Column types and missing values {#column-types}

When a column is present in only one dataset, integer and boolean columns use
nullable types so the other dataset's rows can contain missing values.
For example, `int64` becomes `Int64`, `uint64` becomes `UInt64`, and `bool`
becomes `boolean`. Integer widths and signedness are preserved, avoiding
floating-point conversion and rounding of large integer values.
This schema-based rule also applies when the dataset lacking the column has
no rows. Existing nullable types and source NULLs remain unchanged.

For columns present in both datasets, the inputs' types are reconciled by
pandas as before. This is separate from filling an absent column: combining
integers with floats, or incompatible signed and unsigned integers, can still
produce floats and lose precision. Check and intentionally convert shared
columns to compatible types before concatenating when exact values matter.

Different column layouts require unique column names. Rename duplicate
columns before concatenating datasets with different layouts.

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
| Values appear under separate columns | Column names must match exactly to be combined. Rename columns before concatenating if they represent the same information. |
| Some output cells are missing | One input dataset does not have a column with that name. This is expected when the inputs have different columns. |
| Duplicate rows remain | Concatenate preserves all input rows. Remove duplicates in a separate preparation step if needed. |
| Rows appear in an unexpected order | The active dataset is first, and its rows precede the rows from the selected second dataset. |

For calculated columns, summaries or matching records, see
[Transform data](index.md).

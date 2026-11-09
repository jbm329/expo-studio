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

The preview contains rows for keys present in both datasets:

| join_status | Order ID | Customer ID | Amount | ID | Customer | Region |
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

Integer and boolean columns on the side that can be missing use nullable
types: right-side columns for a left join, left-side columns for a right join,
and both sides for a full join. For example, `int64` becomes `Int64` and `bool`
becomes `boolean`, even when every row matches. This preserves integer
precision without converting integers to floating-point values. Integer widths
and signedness are preserved, and existing nullable types remain unchanged.
Inner joins do not apply this conversion. Neither input dataset is modified.

## Select keys and output columns {#keys-and-columns}

Choose one key column from each dataset. The values to match must have
compatible data types; the dialog enables compatible right-side keys for the
selected left key. Column names do not need to be the same. For example,
**Customer ID** can match **ID**.

The key suggestions are a convenience, not a check that values have the
meaning you intend. Confirm that the selected columns identify the same kind
of entity in both datasets. A key may appear more than once, which can create
more than one output row for a match.

Use the checkboxes under **Columns to include** to choose non-key columns for
the result. The selected key columns and **join_status** are retained
automatically. The status identifies whether a row matched both datasets
(`both`), only the left (`left_only`), or only the right (`right_only`).

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
| Values are missing after a join | An outer, left, or right join retains unmatched rows; inspect **join_status** to see which side had no match. |
| A column name has a dataset suffix | Both datasets contain a selected column with that name. Rename the source columns or use the suffix to distinguish them. |
| The preview estimate differs from the final row count | The preview row sample and estimated row count are not a complete calculation. Review the created result and its **join_status** values. |

For calculated columns, summaries or appending rows, see
[Transform data](index.md).

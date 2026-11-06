# Clean values

Clean a column's text, replace a value, fill missing entries or convert a
column's data type. These operations change the dataset in the active result
tab. Review the result after each change.

Select a **ready result tab**, then right-click the column header. The
available actions depend on the column's type and contents.

## Clean text {#clean-text}

Open **Cleanse data…** on the column-header menu. Its actions include:

| Action | What it does |
|---|---|
| **Trim (remove whitespace)** | Removes whitespace at the start and end of each value. |
| **Normalize whitespace** | Replaces runs of whitespace with one space and trims the ends. |
| **Convert to lowercase**, **Convert to uppercase**, **Convert to title case**, **Capitalize first letter** | Changes the letter case of text values. |
| **Replace text…** | Replaces matching text in the column. |
| **Insert text…** | Inserts text into values at a chosen position. |
| **Remove text (simple)…** | Removes a literal text match. |
| **Remove text (regex)…** | Removes text matching a regular expression. |
| **Keep digits only**, **Keep letters only** | Removes characters that are not digits or letters. |

For example, trimming `"  North  "` gives `"North"`. Normalizing
`"North   Region"` gives `"North Region"`. These are text-cleaning operations;
they are not numeric or date conversions.

## Replace a value from a cell {#replace-value}

To replace a value using a cell as the starting point:

1. Right-click the cell containing the value.
2. Open **Value…** and select **Replace value…**.
3. Enter the new value. Leave **Replace all** unchecked to change only the
   selected cell; check it to replace exact matches throughout that column.
4. Confirm the change.

This cell-menu action uses the selected cell's value as the match. It is not a
substring or regular-expression replacement. The replacement is entered as
text, and the column is converted to text for this operation.

## Fill missing values {#fill-missing}

Right-click a column header and open **Fill missing values…**. The numeric
**Mean**, **Median** and **Mode** actions are available for numeric columns;
**Custom value…** lets you enter a value appropriate to the column's type.
These actions fill missing entries only. If the column has no missing values,
there is nothing to fill.

For example, if a numeric **Amount** column contains `10`, a missing value and
`30`, both its mean and median are `20`. Filling with either replaces the
missing entry with `20`; the existing values stay unchanged. **Mode** uses the
most frequent value.

An empty text value such as `""` is not the same as a missing value. Filling
missing values does not replace empty text.

## Convert a data type {#data-types}

Right-click a column header, open **Datatype…**, then choose an available
conversion:

| Conversion | Notes |
|---|---|
| **Convert to category…** | Store repeated labels as categories; see [Work with categories](#categories) for conversion options and maintenance. |
| **Convert to text (string)** | Treats values as text. |
| **Convert to integer (Int64)** or **Convert to float (Float64)** | Converts numeric-looking values to a numeric type. |
| **Convert to datetime…** or **Convert to date…** | Choose an input format or auto-detection. Date drops the time; datetime keeps it. |
| **Convert to boolean…** | Specify which text values mean True and which mean False. Matching ignores letter case; trim surrounding whitespace first if needed. |

With the default conversion behavior, values that cannot be parsed as a number,
date or boolean become missing. For example, converting text values `12`,
`unknown` and `8` to integers results in `12`, missing and `8`. Inspect the
converted column before using it in calculations or analysis. The menu only
enables conversions supported for the selected column.

## Work with categories {#categories}

A categorical column stores values as labels from a defined list of categories.
For example, a **Priority** column might contain `Low`, `Medium` and `High`.
The category list is separate from the rows: a category can remain in the list
even when no current row uses it.

Category order, row order and column order are different. Setting category
order does not rearrange rows or move the column. Use **Sort ascending** or
**Sort descending** afterward to sort rows by the category list, or
[Order](organize-columns.md#change-column-order) to move the column.

### Convert a column to category {#convert-to-category}

1. Right-click the column header and select **Datatype… → Convert to category…**.
2. Choose a **Category order** and review the checkboxes described below.
3. Select **OK** to convert the column.

The action is offered for eligible text-like columns with repeated values.
It is disabled if the column is already categorical or does not meet the
conversion requirements. Missing entries remain missing, not a category named
`Missing`.

The order options arrange the category list, not the rows:

| Category order | Meaning |
|---|---|
| **Alphabetically** | Sort labels alphabetically. This is the default. |
| **By frequency** | Put the most frequent label first, followed by less frequent labels. |
| **Preserve existing order** | Use the order in which distinct values first appear in the current dataset. |

For example, with values `Medium`, `Low`, `High`, `High`, `High`, `Low`:

| Choice | Category list |
|---|---|
| Alphabetically | High, Low, Medium |
| By frequency | High, Low, Medium |
| Preserve existing order | Medium, Low, High |

**Categories should be ordered** declares that the categories have a meaningful
ranking. Leave it unchecked for labels such as regions; check it for levels
such as priority, then set the intended order explicitly. It is unchecked by
default. Even an unordered categorical column has a category list used when
sorting rows; checking this option does not itself sort the table.

**Strict mode (unknown values → NA)** is checked by default. It describes
converting values outside the category list to missing values. In this
conversion dialog, however, the list is built from all current nonmissing
values. Checking or unchecking strict mode therefore produces the same result
for those values. It is not a rule that validates future edits.

### Rename a category {#rename-category}

1. Right-click the categorical column header and select
   **Datatype… → Rename category…**.
2. Choose the existing label under **Category**.
3. Enter a nonempty **New name**, then select **OK**.

This changes every occurrence of the chosen label in that column, not the
column's name or just one cell. For example, rename `Medium` to `Normal` to
update all Medium priorities.

Renaming to a label that already exists **merges the categories**. Renaming
`Medium` to `High`, for example, leaves both sets of rows labelled `High`.
After a merge, review the category order and set it again if needed.

### Set category order {#set-category-order}

To rank priorities as **Low → Medium → High** rather than alphabetically:

1. Right-click the categorical column header and select
   **Datatype… → Set category order…**.
2. Drag the labels into the desired sequence, or select a label and use
   **Up** and **Down**.
3. Leave **Ordered category** checked to declare a meaningful ranking.
4. Select **OK**. To rearrange the rows too, use **Sort ascending** afterward.

**Sort alphabetically** rearranges the dialog's list.
**Restore original order** restores the list as it was when you opened the
dialog, not necessarily its order when the dataset was first loaded.

| Option | Meaning |
|---|---|
| **Ordered category** | Marks the list as a meaningful ranking. It is checked by default when this dialog opens. |
| **Strict mode (unknown values → NA)** | Converts any value outside the listed categories to missing. It is unchecked by default. |
| **Add missing values last** | With strict mode off, appends observed labels absent from the list, in first-appearance order. It is checked by default. |

Despite its label, **Add missing values last** refers to missing *category
labels*, not missing cells: it neither fills missing entries nor moves them.
It has no effect when strict mode is on. With strict mode off and this option
also off, values outside the list still become missing.

The dialog starts with the complete existing category list and lets you
reorder it, not add or delete labels. Normally, therefore, the strict and
append options do not change any values.

### Remove unused categories {#remove-unused-categories}

After filtering rows, a category may remain defined even though no remaining
row uses it. Right-click the categorical column header and select
**Datatype… → Remove unused categories** to drop these unused labels.

For example, if the category list is `Low`, `Medium`, `High` but the remaining
rows contain only `Low` and `High`, the list becomes `Low`, `High`. This action
does not remove rows, change populated cells or fill missing values. Unlike
**Rename category…** and **Set category order…**, it runs without a configuration
dialog.

## Review or undo a change

Use **Undo** on the toolbar to reverse a recent operation when an undo step is
available. To save the prepared dataset, select its result tab and export it;
see [Export prepared data](../application-overview.md#export-data).

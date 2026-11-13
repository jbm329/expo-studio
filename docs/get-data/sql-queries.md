# Load data with SQL

Use a database query to load rows into a result tab. Configure a named
connection first; see [Database connections](../settings/database-connections.md)
for supported connection types, drivers, authentication and testing.

1. In the workbench's **Database connections** panel, right-click the saved
   connection and select **Connect**.
2. Expand the database and its **Tables** or **Views**. Double-click a table or
   view to put a generated `SELECT` statement in an SQL editor tab.
3. Review the generated statement or write your own query. Confirm the
   connection shown in the editor tab title; if needed, right-click the tab and
   select **Associate with connection**.
4. Select **Run query** to execute the full editor contents, or select SQL text
   and choose **Run selection**. **Run top 10** requests a row-limited result
   from the full query; it does not mean “run the selected text.”
5. Wait for the query to finish, then select its result tab to review the
   returned rows.

Generating SQL from a table or view only prepares text; it does not run the
query. A saved SQL file also opens as editor text and needs an associated
connection before it can run. For editor controls and result-tab behavior, see
[Workbench window](../workbench/index.md#sql-editor).

While you edit a query, the SQL editor highlights its syntax and lints the
text. With a database connection associated with the tab, syntax highlighting
and linting use that connection's SQL dialect. Linting can point out issues
before you run the query, but it does not replace checking the result or any
database-specific errors reported during execution.

## Inspect table and view properties {#object-properties}

For **SQL Server**, **PostgreSQL** and **MySQL/MariaDB** connections, right-click
a table or view in the schema browser and select **Properties**. Other database
types do not yet offer this action. The dialog stays bound to the connection
owning that object, even if you switch SQL editor tabs.

Properties loads catalog metadata in the background. It does not retrieve table
rows, calculate row counts or modify the database.

MySQL/MariaDB Properties supports both `pymysql` and `mysqlconnector`
connections. SQL text, including literal percent signs in metadata queries,
is passed unchanged without parameter interpolation.

- The title bar identifies the object as `Properties (table: name)` or
  `Properties (view: name)`. The full connection/database/schema path is not
  displayed.
- **Description** shows the object's `MS_Description` extended property on
  SQL Server or its native comment on PostgreSQL and MySQL/MariaDB tables.
  Column descriptions use the same database-specific source.
- **Columns** lists column names in database order, complete declared types,
  nullability, default SQL expressions, constraint summaries and descriptions.
  Selecting a column shows its full description, identity/computed expression
  and named extended properties below the grid.
- **Extended properties** lists every visible named property on the object,
  not just `MS_Description`. Column properties appear in the selected-column
  details instead. This tab is hidden for PostgreSQL and MySQL/MariaDB, which
  use native comments rather than SQL Server-style named extended properties.
- **Constraints** shows declared primary keys, foreign keys, unique constraints
  and checks, including names, grouped columns, foreign-key destinations and
  available SQL definitions. A composite unique constraint applies to the
  column combination, not independently to each column. View constraints are
  not inferred from underlying tables.

Select cells in a grid and use **Copy selected cells** to copy tab-separated
text. Descriptions and column details can also be selected and copied. Database
documentation is displayed as plain text, including any markup it contains.

**Not set**, **Not applicable**, **Not supported** and **Unavailable** distinguish
different reasons for missing metadata. Only metadata visible to your database
user is shown: an empty property or constraint list does not prove that no
hidden metadata exists. A column's constraint summary can be empty when no
visible column-associated constraint was found; table-level checks may appear
only in the Constraints tab.

PostgreSQL types use the database's formatted type names, including arrays,
domains, enums, length and precision where declared. Defaults and generated
expressions are shown as SQL rather than evaluated values. Identity columns
show their declared generation mode; legacy `serial` columns expose their
sequence expression as a default. Only declared table constraints are listed,
not inferred constraints on views or separate unique indexes. PostgreSQL
permits zero-column objects, which appear with an empty Columns grid.

MySQL/MariaDB types retain their catalog declaration, including length,
precision, unsigned types and enum values. Table and base-column comments are
shown; empty comments appear as **Not set**. View descriptions and column
comments are **Not supported**, not copied from underlying tables.
`AUTO_INCREMENT` and generated expressions appear in selected-column details.
Key definitions preserve ordered index expressions and prefix lengths. Only
actual indexed column names appear in the Columns field; columns used inside
an expression are not inferred by parsing it.
If an older server identifies a generated column but cannot expose its
expression, the expression is **Unavailable**.

The app discovers available catalog columns before loading MySQL/MariaDB
metadata. CHECK expressions are listed when the server exposes the CHECK
catalog; their column associations are not inferred by parsing SQL. If that
catalog is absent, **Check: Not supported** appears below the tabs, while
available key constraints remain visible. These are declared constraints,
not a statement that enforcement is enabled. A failed discovery or metadata
query is an error, not an empty constraint list.

Defaults are displayed as SQL, preserving expressions and quoting literals
according to the server's catalog conventions. On MariaDB versions before
10.2.7, a present default is **Unavailable**, because the catalog cannot
reliably distinguish literal text from an expression. Metadata rereads detect
changes during loading where possible, but are not a transactional DDL snapshot.

Use **Retry** to reload metadata or recover from a retrieval error. Errors do
not disconnect the database or clear its schema tree. You can close the dialog
while loading. If the connection is disconnected, deleted or its saved settings
are replaced, close the invalidated dialog and reopen Properties after
connecting again. Late replies cannot replace the invalidated display.

## Result datatypes

For SQLite, PostgreSQL, MySQL/MariaDB, DuckDB and ODBC queries, integer values mixed
with NULLs load as nullable pandas integers (`Int64`, or `UInt64` when needed
for unsigned values). Actual boolean values mixed with NULLs load as nullable
`boolean`. Complete integer and boolean columns retain native storage.

Inference follows values returned by the database driver, not column names or
declared table types. Numeric `0`/`1` values are not guessed as booleans.
Empty or all-NULL columns remain `object` when their type cannot be established.
Floating-point, text and mixed-value columns retain their existing inference,
including the existing conversion of Decimal values to floating-point storage
for non-ODBC readers. ODBC retains Decimal objects.

Integer precision is preserved before pandas can promote missing integers to
floating-point storage. This cannot recover precision already lost in a SQL
expression or by a database driver.

## Use SQL autocomplete

Autocomplete also uses the connection's SQL dialect and available schema
metadata. Suggestions appear as you type a period after a schema, table or
table alias: `schema.` offers tables in that schema, `table.` offers its
columns, and `alias.` offers columns from the table referenced by that alias in
the query. Continue typing after the period to narrow the suggestions. Press
**Ctrl+Space** to request suggestions while editing. Suggestions depend on the
connection, query context and metadata available to the editor; they are not a
SQL syntax checker or a list of every object you can query.

![SQL editor showing a query against invoice tables and column-name suggestions for the customer alias.](../assets/get-data/sql_autocomplete.png)

*The suggestions in this example come from the connected database's schema.
Names and available suggestions depend on your connection.*

If expected objects or columns are missing, check the editor's connection and
refresh its schema with **Update schema**. The query still needs to be valid for
the connected database and your permissions.

## Continue your workflow

- [Get data overview](index.md) for other ways to load data.
- [Prepare data](../prepare-data/index.md) or
  [Transform data](../transform-data/index.md) to work with query results.
- [Analyze data](../analyze-data/index.md) or
  [Export data](../export-and-report/index.md) when your dataset is ready.

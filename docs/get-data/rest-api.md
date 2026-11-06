# Load a REST response

Configure and save a request in **Tools → REST connections…** first. The
[REST API connections guide](../workbench/rest-api-connections.md) explains
request fields, authentication, response paths, pagination and the
[SCB query builder](../workbench/rest-api-connections.md#scb-query-builder).

1. In the workbench's **REST connections** panel, find the saved request.
2. Double-click it, or right-click it and select **Load data**.
3. Wait for the background request and conversion to finish, then select the
   result tab.

The configured client supports **GET** and **POST** requests returning JSON.
The response must have a structure the application can convert into a table;
for nested data, configure a response path in the request. Page-number
pagination is available when it matches the API. This is not a general-purpose
client for every HTTP method, response format or API pagination scheme.

**Test** in the REST connections dialog checks one request using the current
form. It does not save the form or create a result tab. Loading a saved request
from the workbench is the step that fetches data into a dataset.

## Continue your workflow

- [Get data overview](index.md) for other ways to load data.
- [Prepare data](../prepare-data/index.md) or
  [Transform data](../transform-data/index.md) to work with the response.
- [Analyze data](../analyze-data/index.md) or
  [Export data](../export-and-report/index.md) when it is ready.

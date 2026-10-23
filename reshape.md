|VårdkontaktId   |PatientId   |KontaktStartad   |Vårdform   |Klinik   |Kontakttyp   |Hallänning   |Yrkesroll   |Vårdtid|
|---|---|---|---|---|---|---|---|---|
|OV_100   |1   |2026-01-01   |Öppenvård   |Vårdcentralen X   |Mottagningsbesök   |1   |Läkare   |   |
|SV_150   |2   |2026-05-15   |Slutenvård   |Medicinkliniken   |Okänd   |0   |Sjuksköterska   |5   |
|OV_200   |3   |2026-06-12   |Akut   |Akuten i Staden   |Okänd   |1   |Okänd   |   |

Above is a typical example of the structure of data that we get raw from our datawarehouse. 

I want to introduce a new feature in my app, "Reshape", which allows users to transform and reshape the data for better analysis and visualization. The "Reshape" feature will enable users to pivot, unpivot, and aggregate data based on their specific needs.

We need to be able to create metrics (SUM, AVG, COUNT, COUNT DISTINCT MAX, MIN) and choose dimensions. Should be able to create metrics like "COUNT DISTINCT VårdkontaktId where yrkesroll = 'Läkare' AND Hallänning = 1". 
Open reshape dialog via toolbar button right after concatenate or context menu rightclick on tab. When reshape is opened only the current active dataset is available. Reshaped dataset should be crated as new tab in ResultTabmanager (See JOIN and Concatenate as reference).

Follow existing architecture and style guidelines for implementing the "Reshape" feature. 

README.md is a source for valuable information.

Do this in steps and after each step, ask for confirmation before proceeding to the next step. DO NOT COMMIT! I will do that manually. Update/add pytests as needed. Make sure targeted ruff format, ruff check ., mypy . and pyright pass after each step.

I have i18n support so each step should include necessary translations for new strings (see readme).

Don't guess or assume, ask for clarification if needed.

Example output:



|PatientId   |Antal mottagningsbesök med läkare   |Antal akutenbesök   |Antal vårddagar slutenvård på medicinkliniken   |
|---|---|---|---|
|1   |10   |2   |6   |
|2   |1   |0   |2   |




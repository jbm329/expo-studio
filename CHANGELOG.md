# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed
- Correlation configured titles use bold text consistently with other analyses, with applied columns shown separately
- Clustering shares configured method titles, applied feature/standardization/applicable-parameter summaries, and descriptive component labels across Analysis, Reports, HTML, and exports; distinct configurations coexist, inactive parameters do not distinguish entries, and reruns require explicit review while preserving notes, components, and order
- PCA shares its title, applied ordered features, standardization, and content-specific component labels across Analysis, Reports, HTML, and exports; distinct configurations coexist and same-configuration reruns require explicit review while preserving notes, components, and order
- Time Series shares applied time/value roles, resampling, automatic or explicit seasonal period, decomposition model, and semantic component labels across Analysis, Reports, HTML, and exports; distinct configurations coexist and identical reruns require explicit review while preserving notes, components, and order
- HTML Strongest correlations tables show the common Ranking and Holm explanation once below the table
- Advanced Analysis now stays bound to the active ready dataset for the whole modal session; report entries share that source
- Advanced Analysis displays the source dataset name and dimensions in the window title instead of a separate dataset pane
- HTML reports show dataset, report generation date, and Expo version once at the top, without row/column metadata
- Correlation presentations share configured method/column labels across Analysis, Reports, HTML, and exports; same-method column changes and reruns require explicit review before replacing a captured report result
- Hypothesis Tests share applied test-family, ordered variable-role, computed-test, and chart-component labels across Analysis, Reports, HTML, and exports; distinct selections coexist and identical reruns require explicit review
- Regression shares applied model, outcome-role, ordered predictor, modeled-term, reference-coding, and component labels across Analysis, Reports, HTML, and exports; distinct full configurations coexist and identical reruns require explicit result review
- Outliers share configured method titles, applied-setting summaries, and content-specific chart labels across Analysis, Reports, HTML, and exports; univariate detail changes replace only the captured detail, while complete screening configurations coexist and identical reruns require explicit review
- HTML hypothesis reports separate captured explanatory notes from actual test-result rows; table exports retain the existing Notes column
- Linear, Logistic, Poisson, Negative Binomial, and Cox share the Model summary heading across Analysis, report selection, HTML, and exports; HTML reports show captured notes below the summary table and omit note-only rows, while table exports retain the existing Notes column and rows
- HTML Outliers reports show captured summary/detail/model notes below their tables, omit note-only rows, and show Status only when unscreened columns need explanations
- HTML clustering reports show captured model notes below Model summary and omit note-only rows; table exports retain the existing Notes column
- HTML PCA reports show captured model notes below Model summary and omit note-only rows; table exports retain the existing Notes column
- HTML Time Series reports show captured model notes below Model summary and omit note-only rows; table exports retain the existing Notes column
- Univariate Outliers detail uses the shared Model summary heading across Analysis, Reports, HTML, and exports

### Added
- Categorical tab in Statistics with frequency counts, percentages, and separate missing-value counts
- Continuous mean/SD and median/quartile summaries with Shapiro-Wilk reporting guidance
- Dataset Overview with dimensions, missingness, duplicates, column profiles, warnings, and first/last 10-row previews and exports (separate Excel sheets or grouped CSV/binary rows, retaining overlap)
- Shapiro-Wilk normality tests and distribution charts for numeric columns
- Welch's t-test for two-group comparisons, with group-level normality checks
- Student's t-test as an equal-variance alternative for two-group comparisons
- Mann-Whitney U test as a nonparametric two-group comparison
- One-way ANOVA for parametric comparisons across three or more groups
- Kruskal-Wallis test as a nonparametric multi-group comparison
- Pearson chi-square test with expected counts and adjusted residuals
- Fisher's exact test guidance and results for applicable 2x2 tables
- Wilcoxon signed-rank test for two repeated measurements
- Friedman test and Kendall's W for three or more repeated measurements, with distribution and subject-trajectory charts
- Pearson, Spearman, and Kendall tau-b correlation matrices with confidence intervals, significance tests, and Holm adjustment
- Multiple linear regression with numeric and categorical predictors, confidence intervals, summaries, and diagnostics
- Logistic regression for binary outcomes with odds ratios, ROC/AUC, and calibration diagnostics
- Poisson regression for count outcomes with rate ratios and dispersion diagnostics
- Negative Binomial regression for overdispersed counts with rate ratios and confidence intervals
- Cox proportional-hazards regression with hazard ratios, forest plots, and Kaplan-Meier survival curves
- Univariate outlier screening using IQR, z-score, and modified z-score methods
- Multivariate outlier detection using Isolation Forest and Local Outlier Factor
- K-means, DBSCAN, and agglomerative clustering with cluster summaries and PCA projections
- PCA with optional standardization, explained variance, feature loadings, and score plots
- Time-series preparation with optional resampling, autocorrelation, and additive or multiplicative seasonal decomposition
- Time-series export and report presentation for applied settings, including automatic-period intent and unavailable diagnostics without implying that decomposition was calculated
- Export for all nine analyses: applied-result tables and available charts in Excel; one table per CSV or binary export
- Session report drafts for all nine analyses with selected components, notes, metadata, ordering, and asynchronous in-app HTML preview
- Correlation report entries show their applied method and ordered columns; different methods coexist while column changes and rerun captures can be explicitly replaced or updated
- Self-contained HTML report saving with background generation, safe replacement, and automatic opening in the default browser
- Consistent Analysis configuration pane widths, adaptive layouts, and scrolling

## [1.0.0] - 2026-10-06

### Added
- SQL editor with syntax highlighting, autocomplete, and linting
- Data import from files and databases
- REST API data loading
- Join and concat operations
- Pandas DataFrame support
- Derived columns
- Dataset overview analysis
- Descriptive statistics
- Distribution analysis
- Normality testing (Shapiro-Wilk)
- Group comparison and hypothesis testing
- Chi-square tests
- Correlation explorer
- Linear regression
- Univariate and multivariate outlier analysis

### Technical
- Async job framework
- Pending result tabs
- Internationalization (i18n)
- GitHub Actions CI/CD
- Cross-platform packaging

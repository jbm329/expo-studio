# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Categorical tab in Statistics with frequency counts, percentages, and separate missing-value counts
- Continuous summaries with Shapiro-Wilk-guided mean/SD or median/quartile reporting and a manual override
- Student's t-test alongside Welch's t-test and Mann-Whitney U for two-group comparisons
- Guidance on Fisher's exact test for 2x2 tables with small expected counts
- Paired comparison using Wilcoxon signed-rank tests for two measurement occasions
- Paired comparison using Friedman tests and Kendall's W for three or more measurement occasions
- Paired measurement summaries, distribution boxplots, and subject trajectory charts
- Logistic regression for binary outcomes with odds ratios and confidence intervals
- Poisson regression for count outcomes with rate ratios and advisory dispersion diagnostics
- Poisson observed-versus-fitted count and Pearson residual charts
- Negative Binomial regression for overdispersed count outcomes with rate ratios and confidence intervals
- Negative Binomial observed-versus-fitted count and variance-adjusted Pearson residual charts
- Cox proportional-hazards regression with duration/event configuration, hazard ratios, and confidence intervals
- Cox hazard-ratio forest plots and unadjusted Kaplan-Meier curves with censoring marks and numbers at risk
- Consistent Analysis configuration pane widths, adaptive layouts, and scrolling
- Full-text hover tooltips for Analysis dropdowns, preserving disabled-option explanations

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

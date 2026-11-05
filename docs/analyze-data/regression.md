# Regression

Use **Regression** to model an outcome from one or more predictors. Choose a
model and outcome, select predictors, then select **Apply**. The model
selector offers linear, logistic, Poisson, negative-binomial and Cox
regression.

## Choose a model and outcome {#choose-model}

| Model | Outcome selection |
|---|---|
| Linear | A numeric target. |
| Logistic | A binary target with two observed values. |
| Poisson | A numeric, non-negative integer count target. |
| Negative binomial | A numeric, non-negative integer count target. |
| Cox | A numeric duration and a separate binary event column; event values use `1` for an event and `0` for censored. |

Targets available in the selector depend on their column types and values.
For Cox, choose **Duration** and **Event** rather than a single target.
Duration values must be positive; nonmissing invalid duration or event
values are reported as errors rather than silently treated as missing.

## Select predictors {#select-predictors}

Numeric columns can be used as numeric predictors. Text, category and
Boolean columns can be used as categorical predictors when they have 2–50
distinct non-missing values. Date/time and ineligible high-cardinality
columns are not offered as predictors. A categorical predictor is encoded
relative to a reference level.

Up to 20 predictors can be selected. Expanded models are also limited to
50 non-intercept terms: a categorical predictor with *k* levels contributes
*k − 1* terms. The term limit can therefore be reached before selecting 20
columns. The intercept is not included in the 50-term cap.

## Interpret the fit and diagnostics {#interpret}

The results depend on the selected model. Linear Regression reports
coefficients, fit metrics and residual diagnostics. Logistic and count
models report model terms and model-specific fit information; count models
also report an overdispersion diagnostic. Cox Regression reports hazard
ratios, model metrics and charts.

For linear, logistic and count fits, rows missing or containing non-finite
values in the outcome or any selected predictor are excluded listwise. Cox
regression also excludes missing rows, but rejects nonmissing invalid
duration or event values. The result reports rows used and dropped. Cox
regression also needs more complete cases and events than expanded model
terms. Review warnings and diagnostics as model checks, not as proof that
all assumptions are satisfied. The selected model is retained; an
overdispersion warning does not silently switch a Poisson model to another
family.

Coefficient confidence intervals are 95%. For linear regression, the
multicollinearity warning flags a variance inflation factor greater than 10;
the autocorrelation warning is raised when Durbin-Watson is below 1.5 or
above 2.5. Treat these diagnostic thresholds as screening prompts, not
automatic proof that a model is invalid.

## Fit and chart limits {#limits}

| Limit | Effect |
|---|---|
| 20 selected predictors | Applies to linear, generalized and Cox regression. |
| 50 expanded non-intercept terms | Applies after categorical predictors are dummy-coded. |
| 200 optimizer iterations | Maximum for logistic, Poisson, negative-binomial and Cox fitting. A fit that does not converge is reported as a failure, not a successful result. |
| 5,000 plot points | Linear and count-model diagnostic plots use at most this many complete rows. Model fits and statistics still use every complete row. |
| 10 calibration bins | Logistic calibration uses at most 10 bins; the ROC/AUC calculation uses the fitted cohort. Tied probabilities can produce fewer bins. |

## Export {#export}

After a successful fit, select **Export** for available model tables and
charts. Exports use the applied model and result.

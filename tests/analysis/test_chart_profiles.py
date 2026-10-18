from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from expo_jbm329.services.analysis.chart_profiles import (
    CLUSTERING_PROJECTION_PROFILE,
    CORRELATION_CHART_PROFILE,
    HYPOTHESIS_CHART_PROFILE,
    OUTLIER_HISTOGRAM_PROFILE,
    OUTLIER_PROJECTION_PROFILE,
    PCA_CHART_PROFILE,
    REGRESSION_COUNT_PROFILE,
    REGRESSION_LINEAR_PROFILE,
    REGRESSION_SURVIVAL_PROFILE,
    STATISTICS_CHART_PROFILE,
    TIME_SERIES_CHART_PROFILE,
    TIME_SERIES_DECOMPOSITION_PROFILE,
    regression_logistic_profile,
)


@pytest.mark.parametrize(
    ("profile", "expected_pixels"),
    [
        (STATISTICS_CHART_PROFILE, (1080, 420)),
        (HYPOTHESIS_CHART_PROFILE, (1080, 420)),
        (CORRELATION_CHART_PROFILE, (1080, 720)),
        (CLUSTERING_PROJECTION_PROFILE, (960, 720)),
        (OUTLIER_HISTOGRAM_PROFILE, (960, 450)),
        (OUTLIER_PROJECTION_PROFILE, (960, 720)),
        (PCA_CHART_PROFILE, (960, 600)),
        (TIME_SERIES_CHART_PROFILE, (960, 480)),
        (TIME_SERIES_DECOMPOSITION_PROFILE, (960, 960)),
        (REGRESSION_LINEAR_PROFILE, (1620, 540)),
        (REGRESSION_SURVIVAL_PROFILE, (1440, 720)),
        (REGRESSION_COUNT_PROFILE, (1320, 570)),
    ],
)
def test_export_profiles_preserve_existing_image_geometry(profile, expected_pixels):
    assert profile.geometry.pixel_size == expected_pixels
    assert profile.geometry.constrained_layout


@pytest.mark.parametrize("predictors", [0, 1, 10, 20, 100])
def test_logistic_geometry_retains_predictor_dependent_height(predictors):
    geometry = regression_logistic_profile(predictors).geometry
    assert geometry.figsize == (10, max(7.5, 5 + predictors * 0.24))
    assert geometry.pixel_size == (1200, round(max(7.5, 5 + predictors * 0.24) * 120))


def test_profile_geometry_is_immutable_and_invalid_predictor_counts_fail():
    with pytest.raises(FrozenInstanceError):
        PCA_CHART_PROFILE.geometry.dpi = 300
    with pytest.raises(ValueError, match="negative"):
        regression_logistic_profile(-1)

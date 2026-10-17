from dataclasses import FrozenInstanceError

import pytest

from expo_jbm329.services.analysis.chart_config import (
    DEFAULT_AXIS_POLICY,
    DEFAULT_CHART_CONFIG,
    AxisPolicy,
    AxisRole,
    ChartConfig,
    RotationMode,
)


def test_defaults_are_immutable_and_use_renderer_aware_auto_rotation():
    assert DEFAULT_CHART_CONFIG.default_axis_policy == DEFAULT_AXIS_POLICY
    assert DEFAULT_AXIS_POLICY.rotation_mode is RotationMode.AUTO
    assert DEFAULT_AXIS_POLICY.role is AxisRole.CATEGORICAL
    assert DEFAULT_CHART_CONFIG.overlap_gap_points == 2.0

    with pytest.raises(FrozenInstanceError):
        DEFAULT_CHART_CONFIG.overlap_gap_points = 1.0


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"overlap_gap_points": -1.0}, "overlap gap"),
        ({"overlap_gap_points": float("inf")}, "overlap gap"),
    ],
)
def test_chart_config_rejects_invalid_bounds(kwargs, message):
    with pytest.raises(ValueError, match=message):
        ChartConfig(**kwargs)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"fixed_rotation_degrees": float("nan")}, "rotation"),
        ({"overlap_gap_points": -0.1}, "overlap gap"),
        ({"overlap_gap_points": float("inf")}, "overlap gap"),
    ],
)
def test_axis_policy_rejects_nonfinite_angles_and_invalid_gaps(kwargs, message):
    with pytest.raises(ValueError, match=message):
        AxisPolicy(**kwargs)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"rotation_mode": "auto"}, "Axis rotation mode"),
        ({"rotation_mode": "diagonal"}, "Axis rotation mode"),
        ({"role": "categorical"}, "Axis role"),
    ],
)
def test_axis_policy_rejects_untyped_mode_and_role_values(kwargs, message):
    with pytest.raises(TypeError, match=message):
        AxisPolicy(**kwargs)


def test_chart_config_rejects_non_policy_default():
    with pytest.raises(TypeError, match="Default axis policy"):
        ChartConfig(default_axis_policy="auto")


def test_axis_policy_supports_exclusion_and_fixed_angle():
    excluded = AxisPolicy(role=AxisRole.EXCLUDED)
    fixed = AxisPolicy(rotation_mode=RotationMode.FIXED, fixed_rotation_degrees=37.5)

    assert excluded.role is AxisRole.EXCLUDED
    assert fixed.rotation_mode is RotationMode.FIXED
    assert fixed.fixed_rotation_degrees == 37.5

"""地形剖面表示、参考线余隙折算与剖面输入校验测试。"""

import math

import pytest

from app.profile import ProfilePoint, TerrainProfile, excess_height_m, reference_height_m
from app.profile_validation import validate_terrain_profile
from app.validation import ValidationError

BASE = dict(
    path_length_m=8000.0,
    tx_antenna_height_m=20.0,
    tx_site_elevation_m=100.0,
    rx_antenna_height_m=30.0,
    rx_site_elevation_m=150.0,
)


def _points(*pairs):
    return [tuple(p) for p in pairs]


def test_reference_height_is_linear_between_endpoints():
    """参考线是两端点之间的直线，可在任意里程取值。"""
    assert reference_height_m(0.0, 10.0, 10000.0, 210.0, 0.0) == 10.0
    assert reference_height_m(0.0, 10.0, 10000.0, 210.0, 5000.0) == 110.0
    assert reference_height_m(0.0, 10.0, 10000.0, 210.0, 10000.0) == 210.0


def test_excess_height_sign_convention():
    """超出高度 = 海拔 − 参考线高度：正为咬进，负为余隙。"""
    assert excess_height_m(5000.0, 130.0, 0.0, 10.0, 10000.0, 210.0) == 20.0
    assert excess_height_m(5000.0, 90.0, 0.0, 10.0, 10000.0, 210.0) == -20.0


def test_validate_profile_derives_antenna_tops():
    """天线顶海拔 = 所在地海拔 + 架设高度。"""
    profile = validate_terrain_profile(
        **BASE, points=_points((2000.0, 110.0), (4000.0, 155.0), (6000.0, 140.0))
    )
    assert isinstance(profile, TerrainProfile)
    assert profile.tx_top_m == 120.0
    assert profile.rx_top_m == 180.0
    assert [p.distance_m for p in profile.points] == [2000.0, 4000.0, 6000.0]
    assert all(isinstance(p, ProfilePoint) for p in profile.points)


def test_empty_profile_is_valid_and_means_full_los():
    """没有采样点等价于全程通视（由上层合成出 0 dB）。"""
    profile = validate_terrain_profile(**BASE, points=[])
    assert profile.points == ()


@pytest.mark.parametrize("bad", [0.0, -1.0, float("inf"), float("nan")])
def test_non_positive_or_nonfinite_path_length_rejected(bad):
    with pytest.raises(ValidationError) as excinfo:
        validate_terrain_profile(**{**BASE, "path_length_m": bad}, points=[])
    assert "path_length_m" in excinfo.value.reason


@pytest.mark.parametrize("field", ["tx_antenna_height_m", "rx_antenna_height_m"])
def test_negative_antenna_height_rejected(field):
    with pytest.raises(ValidationError) as excinfo:
        validate_terrain_profile(**{**BASE, field: -0.5}, points=[])
    assert field in excinfo.value.reason
    assert "不能为负" in excinfo.value.reason


def test_zero_antenna_height_allowed():
    """架设高度不为负即可，贴地（0 m）合法。"""
    profile = validate_terrain_profile(
        **{**BASE, "tx_antenna_height_m": 0.0, "rx_antenna_height_m": 0.0}, points=[]
    )
    assert profile.tx_top_m == 100.0
    assert profile.rx_top_m == 150.0


@pytest.mark.parametrize("field", ["tx_site_elevation_m", "rx_site_elevation_m"])
@pytest.mark.parametrize("bad", [float("inf"), float("nan")])
def test_nonfinite_site_elevation_rejected(field, bad):
    with pytest.raises(ValidationError) as excinfo:
        validate_terrain_profile(**{**BASE, field: bad}, points=[])
    assert field in excinfo.value.reason


def test_duplicate_distance_rejected_as_not_strictly_increasing():
    with pytest.raises(ValidationError) as excinfo:
        validate_terrain_profile(
            **BASE, points=_points((2000.0, 110.0), (2000.0, 120.0))
        )
    assert "points[1].distance_m" in excinfo.value.reason
    assert "严格递增" in excinfo.value.reason


def test_decreasing_distance_rejected():
    with pytest.raises(ValidationError) as excinfo:
        validate_terrain_profile(
            **BASE, points=_points((4000.0, 110.0), (3000.0, 120.0))
        )
    assert "points[1].distance_m" in excinfo.value.reason
    assert "严格递增" in excinfo.value.reason


@pytest.mark.parametrize("bad", [0.0, -100.0, 8000.0, 9000.0])
def test_distance_outside_tx_rx_rejected(bad):
    """采样点里程必须落在收发之间（不含两端）。"""
    with pytest.raises(ValidationError) as excinfo:
        validate_terrain_profile(**BASE, points=_points((bad, 100.0)))
    assert "points[0].distance_m" in excinfo.value.reason
    assert "收发之间" in excinfo.value.reason


@pytest.mark.parametrize("bad", [float("inf"), float("nan")])
def test_nonfinite_point_fields_rejected(bad):
    with pytest.raises(ValidationError) as excinfo:
        validate_terrain_profile(**BASE, points=_points((1000.0, bad)))
    assert "points[0].elevation_m" in excinfo.value.reason
    with pytest.raises(ValidationError) as excinfo:
        validate_terrain_profile(**BASE, points=_points((bad, 100.0)))
    assert "points[0].distance_m" in excinfo.value.reason


def test_malformed_point_rejected():
    with pytest.raises(ValidationError) as excinfo:
        validate_terrain_profile(**BASE, points=[(1000.0, 100.0, 5.0)])
    assert "points[0]" in excinfo.value.reason

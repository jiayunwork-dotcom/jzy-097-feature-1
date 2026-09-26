"""地形剖面表示、余隙折算与校验的测试。"""

import math

import pytest

from app.profile import (
    ProfileGeometry,
    ProfileSample,
    reference_line_height_at,
    validate_profile,
)
from app.validation import ValidationError


def _profile(
    samples,
    *,
    freq=900.0,
    length=10000.0,
    tx_ground=0.0,
    tx_h=0.0,
    rx_ground=0.0,
    rx_h=0.0,
):
    return validate_profile(
        frequency_mhz=freq,
        path_length_m=length,
        tx_ground_elevation_m=tx_ground,
        tx_antenna_height_m=tx_h,
        rx_ground_elevation_m=rx_ground,
        rx_antenna_height_m=rx_h,
        profile_samples=samples,
    )


def test_flat_los_excess_height_matches_terrain_elevation():
    """两端天线顶等高时，直视线水平，超出高度即地形海拔（遮挡为正）。"""
    p = _profile([(2000.0, 8.0), (5000.0, -3.0)])
    assert p.excess_height_at(2000.0, 8.0) == 8.0
    assert p.excess_height_at(5000.0, -3.0) == -3.0
    assert list(p.excess_height_at(s.distance_m, s.ground_elevation_m)
               for s in p.samples) == [8.0, -3.0]


def test_slanted_los_excess_height_linear_reference():
    """直视线倾斜时参考海拔沿里程线性插值，服务自行折算余隙。"""
    # Tx 天线顶 120，Rx 天线顶 60，链路长 7000
    p = _profile(
        [(3000.0, 110.0)],
        length=7000.0,
        tx_ground=100.0,
        tx_h=20.0,
        rx_ground=50.0,
        rx_h=10.0,
    )
    los_at_bump = 120.0 + (60.0 - 120.0) * 3000.0 / 7000.0
    assert math.isclose(p.reference_height_at(3000.0), los_at_bump, rel_tol=1e-12)
    assert math.isclose(p.excess_height_at(3000.0, 110.0), 110.0 - los_at_bump)


def test_antenna_top_is_ground_plus_height():
    p = _profile([], tx_ground=100.0, tx_h=25.0, rx_ground=50.0, rx_h=15.0)
    assert p.tx_antenna_elevation_m == 125.0
    assert p.rx_antenna_elevation_m == 65.0


def test_reference_line_height_linear():
    h = reference_line_height_at(100.0, 10.0, 900.0, 50.0, 500.0)
    assert h == 30.0


def test_empty_profile_is_valid_and_clear():
    """没有采样点：无地形可遮挡，视为全程通视（由评估层出零损耗）。"""
    p = _profile([])
    assert p.samples == ()
    assert len(p.samples) == 0


@pytest.mark.parametrize(
    "bad,field",
    [
        (0.0, "path_length_m"),
        (-100.0, "path_length_m"),
        (float("inf"), "path_length_m"),
        (float("nan"), "path_length_m"),
    ],
)
def test_non_positive_or_nonfinite_path_length_rejected(bad, field):
    with pytest.raises(ValidationError) as excinfo:
        _profile([], length=bad)
    assert field in excinfo.value.reason


@pytest.mark.parametrize("bad", [0.0, -900.0, float("inf"), float("nan")])
def test_non_positive_frequency_rejected(bad):
    with pytest.raises(ValidationError) as excinfo:
        _profile([], freq=bad)
    assert "frequency_mhz" in excinfo.value.reason


@pytest.mark.parametrize("side", ["tx", "rx"])
def test_negative_antenna_height_rejected(side):
    kwargs = {}
    if side == "tx":
        kwargs["tx_h"] = -1.0
    else:
        kwargs["rx_h"] = -1.0
    with pytest.raises(ValidationError) as excinfo:
        _profile([], **kwargs)
    assert f"{side}_antenna_height_m" in excinfo.value.reason


def test_zero_antenna_height_allowed():
    p = _profile([], tx_h=0.0, rx_h=0.0)
    assert p.tx_antenna_elevation_m == 0.0


def test_non_finite_ground_elevation_rejected():
    with pytest.raises(ValidationError) as excinfo:
        _profile([], tx_ground=float("nan"))
    assert "tx_ground_elevation_m" in excinfo.value.reason


def test_sample_outside_link_rejected():
    with pytest.raises(ValidationError) as excinfo:
        _profile([(10000.0, 5.0)])  # 里程等于链路长度（必须严格落在内部）
    assert "profile[0].distance_m" in excinfo.value.reason
    with pytest.raises(ValidationError) as excinfo:
        _profile([(0.0, 5.0)])  # 里程为 0（端点由 tx/rx 给出）
    assert "profile[0].distance_m" in excinfo.value.reason


def test_non_strictly_increasing_mileage_rejected():
    with pytest.raises(ValidationError) as excinfo:
        _profile([(1000.0, 5.0), (1000.0, 6.0)])
    assert "profile[1].distance_m" in excinfo.value.reason
    assert "递增" in excinfo.value.reason


def test_decreasing_mileage_rejected():
    with pytest.raises(ValidationError) as excinfo:
        _profile([(3000.0, 5.0), (2000.0, 6.0)])
    assert "profile[1].distance_m" in excinfo.value.reason


def test_non_finite_sample_values_rejected():
    with pytest.raises(ValidationError) as excinfo:
        _profile([(1000.0, float("inf"))])
    assert "profile[0].elevation_m" in excinfo.value.reason
    with pytest.raises(ValidationError) as excinfo:
        _profile([(float("nan"), 5.0)])
    assert "profile[0].distance_m" in excinfo.value.reason


def test_malformed_sample_rejected():
    with pytest.raises(ValidationError):
        _profile([(1000.0,)])
    with pytest.raises(ValidationError):
        _profile("not-a-list")


def test_sample_indices_preserved():
    p = _profile([(1000.0, 1.0), (2000.0, 2.0)])
    assert [s.index for s in p.samples] == [0, 1]
    assert isinstance(p.samples[0], ProfileSample)
    assert isinstance(p, ProfileGeometry)

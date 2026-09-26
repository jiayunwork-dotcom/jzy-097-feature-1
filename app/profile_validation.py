"""地形剖面输入校验。

校验规则（任一不满足即抛 ValidationError，由接口层转成带原因的错误
JSON 拒绝，口径与单刃校验一致）：
- path_length_m 必须为正的有限数；
- 两端天线架设高度必须为有限数且不为负；
- 两端所在地海拔必须为有限数；
- 每个采样点的里程必须为有限数、落在收发之间 (0, path_length_m)、
  且沿剖面严格递增；
- 每个采样点的海拔必须为有限数。

频率的校验复用 validation.validate_frequency，不在此重复。
"""

from __future__ import annotations

import math
from typing import Iterable, Tuple

from .profile import ProfilePoint, TerrainProfile
from .validation import ValidationError


def _require_finite(name: str, value: float) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValidationError(f"{name} 必须是数值，收到 {value!r}")
    if not math.isfinite(value):
        raise ValidationError(f"{name} 必须是有限数值，收到 {value!r}")
    return float(value)


def _require_finite_positive(name: str, value: float) -> float:
    value = _require_finite(name, value)
    if value <= 0.0:
        raise ValidationError(f"{name} 必须为正数，收到 {value!r}")
    return value


def _require_finite_non_negative(name: str, value: float) -> float:
    value = _require_finite(name, value)
    if value < 0.0:
        raise ValidationError(f"{name} 不能为负数，收到 {value!r}")
    return value


def validate_terrain_profile(
    path_length_m: float,
    tx_antenna_height_m: float,
    tx_site_elevation_m: float,
    rx_antenna_height_m: float,
    rx_site_elevation_m: float,
    points: Iterable[Tuple[float, float]],
) -> TerrainProfile:
    """校验并构造地形剖面。points 为 (里程, 海拔) 序列，按里程排列。"""
    path_length = _require_finite_positive("path_length_m", path_length_m)
    tx_top = _require_finite_non_negative(
        "tx_antenna_height_m", tx_antenna_height_m
    ) + _require_finite("tx_site_elevation_m", tx_site_elevation_m)
    rx_top = _require_finite_non_negative(
        "rx_antenna_height_m", rx_antenna_height_m
    ) + _require_finite("rx_site_elevation_m", rx_site_elevation_m)

    validated: list[ProfilePoint] = []
    prev_distance = 0.0  # 发射端里程
    for idx, raw in enumerate(points):
        try:
            raw_distance, raw_elevation = raw
        except (TypeError, ValueError):
            raise ValidationError(
                f"points[{idx}] 必须是 (distance_m, elevation_m) 二元组，收到 {raw!r}"
            )
        distance_name = f"points[{idx}].distance_m"
        distance = _require_finite(distance_name, raw_distance)
        if distance <= 0.0 or distance >= path_length:
            raise ValidationError(
                f"{distance_name} 必须落在收发之间 (0, {path_length})，收到 {distance}"
            )
        if distance <= prev_distance:
            raise ValidationError(
                f"{distance_name} 必须严格递增，前一个采样点里程为 {prev_distance}，"
                f"收到 {distance}"
            )
        elevation = _require_finite(f"points[{idx}].elevation_m", raw_elevation)
        validated.append(ProfilePoint(distance_m=distance, elevation_m=elevation))
        prev_distance = distance

    return TerrainProfile(
        path_length_m=path_length,
        tx_top_m=tx_top,
        rx_top_m=rx_top,
        points=tuple(validated),
    )

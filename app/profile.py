"""地形剖面的表示与余隙折算。

多刃评估的输入不再是调用方预先折算好的「障碍到两端距离 + 超出高度」
标量，而是一条沿收发路径按里程排列的地形剖面：

- 每个采样点只带 (到发射端的水平里程, 该点地面海拔)；
- 收发两端另给所在地海拔与天线架设高度，两端天线顶的连线即直视线；
- 各采样点相对直视线的超出高度 h（遮挡为正、低于直视线为负）由本
  模块折算，几何约定与单刃内核 LinkGeometry 完全一致。

采样点之间不做任何地形插值：障碍只可能落在给定采样点上。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from .validation import (
    ValidationError,
    _require_finite,
    _require_finite_positive,
)


@dataclass(frozen=True)
class ProfileSample:
    """剖面上的一个地形采样点。

    - index: 该点在原始输入剖面中的序号（0 起），对外定位用；
    - distance_m: 到发射端的水平里程，严格位于收发两端之间；
    - ground_elevation_m: 该点的地面海拔（任意有限值，允许负海拔）。
    """

    index: int
    distance_m: float
    ground_elevation_m: float


@dataclass(frozen=True)
class ProfileGeometry:
    """校验后的整条链路剖面几何。

    直视线参考由两端天线顶海拔确定：
        z_tx = tx_ground_elevation_m + tx_antenna_height_m
        z_rx = rx_ground_elevation_m + rx_antenna_height_m
    """

    frequency_mhz: float
    path_length_m: float
    tx_antenna_elevation_m: float
    rx_antenna_elevation_m: float
    samples: tuple[ProfileSample, ...]

    def reference_height_at(self, distance_m: float) -> float:
        """全链路直视线（两端天线顶连线）在指定里程处的海拔。"""
        return reference_line_height_at(
            0.0,
            self.tx_antenna_elevation_m,
            self.path_length_m,
            self.rx_antenna_elevation_m,
            distance_m,
        )

    def excess_height_at(self, distance_m: float, ground_elevation_m: float) -> float:
        """给定点相对全链路直视线的超出高度（遮挡为正）。"""
        return ground_elevation_m - self.reference_height_at(distance_m)


def reference_line_height_at(
    left_distance_m: float,
    left_height_m: float,
    right_distance_m: float,
    right_height_m: float,
    distance_m: float,
) -> float:
    """任意一段子链路参考线（两端点连线）在 distance_m 处的海拔。

    子链路端点可以是天线顶，也可以是主障碍的山顶——折算式子相同。
    """

    span = right_distance_m - left_distance_m
    ratio = (distance_m - left_distance_m) / span
    return left_height_m + (right_height_m - left_height_m) * ratio


def _require_finite_non_negative(name: str, value: float) -> float:
    """天线高度：有限数值且非负（允许贴地架设 0 m）。"""
    finite = _require_finite(name, value)
    if finite < 0.0:
        raise ValidationError(f"{name} 必须为非负数，收到 {value!r}")
    return finite


def _validate_profile_samples(
    samples: Sequence[tuple[float, float]], path_length_m: float
) -> tuple[ProfileSample, ...]:
    if not isinstance(samples, (list, tuple)):
        raise ValidationError(f"profile 必须是采样点列表，收到 {type(samples).__name__}")

    validated: list[ProfileSample] = []
    prev_distance: float | None = None
    for i, raw in enumerate(samples):
        if not isinstance(raw, (list, tuple)) or len(raw) != 2:
            raise ValidationError(
                f"profile[{i}] 必须是 [里程, 海拔] 形式的采样点，收到 {raw!r}"
            )
        raw_distance, raw_elevation = raw
        distance_m = _require_finite(f"profile[{i}].distance_m", raw_distance)
        elevation_m = _require_finite(f"profile[{i}].elevation_m", raw_elevation)
        if not (0.0 < distance_m < path_length_m):
            raise ValidationError(
                f"profile[{i}].distance_m 必须严格落在收发之间 "
                f"(0, {path_length_m})，收到 {distance_m}"
            )
        if prev_distance is not None and distance_m <= prev_distance:
            raise ValidationError(
                f"profile[{i}].distance_m 里程必须严格递增，收到 {distance_m}，"
                f"不大于前一点里程 {prev_distance}"
            )
        validated.append(
            ProfileSample(
                index=i,
                distance_m=distance_m,
                ground_elevation_m=elevation_m,
            )
        )
        prev_distance = distance_m
    return tuple(validated)


def validate_profile(
    frequency_mhz: float,
    path_length_m: float,
    tx_ground_elevation_m: float,
    tx_antenna_height_m: float,
    rx_ground_elevation_m: float,
    rx_antenna_height_m: float,
    profile_samples: Sequence[tuple[float, float]],
) -> ProfileGeometry:
    """校验整条剖面输入并构造 ProfileGeometry。

    校验口径与单刃输入一致：非数值/非有限数/非正频率与链路长度一律
    以带原因的 ValidationError 拒绝；天线高度额外要求非负；采样点
    里程必须严格递增且严格落在收发之间。空剖面合法（视为全程通视）。
    """

    frequency = _require_finite_positive("frequency_mhz", frequency_mhz)
    path_length = _require_finite_positive("path_length_m", path_length_m)
    tx_ground = _require_finite("tx_ground_elevation_m", tx_ground_elevation_m)
    tx_height = _require_finite_non_negative("tx_antenna_height_m", tx_antenna_height_m)
    rx_ground = _require_finite("rx_ground_elevation_m", rx_ground_elevation_m)
    rx_height = _require_finite_non_negative("rx_antenna_height_m", rx_antenna_height_m)
    samples = _validate_profile_samples(profile_samples, path_length)

    return ProfileGeometry(
        frequency_mhz=frequency,
        path_length_m=path_length,
        tx_antenna_elevation_m=tx_ground + tx_height,
        rx_antenna_elevation_m=rx_ground + rx_height,
        samples=samples,
    )


def excess_heights_above_los(profile: ProfileGeometry) -> Iterable[float]:
    """各采样点相对全链路直视线的超出高度（遮挡为正），按里程顺序。"""
    for sample in profile.samples:
        yield profile.excess_height_at(sample.distance_m, sample.ground_elevation_m)

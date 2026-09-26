"""多刃剖面评估编排：校验 → 逐层摊障碍 → 级联合成总损耗。

单刃是多刃的退化特例：剖面里只有一处凸起时，主障碍即该凸起，
两段子链路里再没有别的点高出各自参考线，总损耗就是这一处障碍
喂给单刃内核得到的损耗。全程通视时摊不出任何障碍，总损耗为 0 dB。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Tuple

from .combine import combine_edge_losses
from .fresnel import wavelength_m
from .multiedge import find_obstacles
from .profile_validation import validate_terrain_profile
from .validation import validate_frequency


@dataclass(frozen=True)
class ProfileObstacle:
    """输出用的障碍条目：位置 + 子链路几何 + 菲涅尔参数 + 分摊损耗。"""

    sample_index: int  # 对应剖面 points 的下标
    distance_m: float  # 里程（到发射端的水平距离），m
    depth: int  # 选取层深：0 为全链路主障碍
    d1_m: float  # 子链路内到左端点的水平距离，m
    d2_m: float  # 子链路内到右端点的水平距离，m
    h_m: float  # 相对子链路参考直视线的超出高度，m
    v: float  # 相对所在子链路参考线的菲涅尔参数
    loss_db: float  # 这一处障碍贡献的附加损耗，dB


@dataclass(frozen=True)
class ProfileAssessment:
    """多刃剖面评估结果：总附加损耗、通视判定与障碍分摊明细。"""

    path_length_m: float
    frequency_mhz: float
    wavelength_m: float
    total_loss_db: float
    is_los: bool
    obstacles: tuple[ProfileObstacle, ...]


def assess_profile(
    path_length_m: float,
    tx_antenna_height_m: float,
    tx_site_elevation_m: float,
    rx_antenna_height_m: float,
    rx_site_elevation_m: float,
    frequency_mhz: float,
    points: Iterable[Tuple[float, float]],
) -> ProfileAssessment:
    """评估整条地形剖面的多刃绕射附加损耗。

    points 为 (里程, 海拔) 序列；余隙折算、障碍选取与损耗合成全部
    由服务完成，调用方不需要预先折算任何几何量。
    """
    profile = validate_terrain_profile(
        path_length_m,
        tx_antenna_height_m,
        tx_site_elevation_m,
        rx_antenna_height_m,
        rx_site_elevation_m,
        points,
    )
    freq = validate_frequency(frequency_mhz)
    obstacles = find_obstacles(profile, freq)
    combined = combine_edge_losses(obstacles)
    entries = tuple(
        ProfileObstacle(
            sample_index=o.sample_index,
            distance_m=o.distance_m,
            depth=o.depth,
            d1_m=o.d1_m,
            d2_m=o.d2_m,
            h_m=o.h_m,
            v=o.v,
            loss_db=loss,
        )
        for o, loss in zip(obstacles, combined.per_obstacle_db)
    )
    return ProfileAssessment(
        path_length_m=profile.path_length_m,
        frequency_mhz=freq,
        wavelength_m=wavelength_m(freq),
        total_loss_db=combined.total_db,
        # 摊不出障碍 ⟺ 所有采样点都在直视线下方 ⟺ 通视
        is_los=not entries,
        obstacles=entries,
    )

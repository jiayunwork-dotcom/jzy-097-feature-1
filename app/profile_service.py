"""多刃剖面评估编排：校验剖面、逐层选障碍、合成总损耗。

这是在既有单刃评估（app.service）之上新增的一层，不改动旧接口：
输入整条地形剖面，内部自行折算余隙、递归选取主障碍，输出总附加
损耗、通视判定与每一个被选中障碍的明细。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .fresnel import wavelength_m
from .multiedge import SelectedObstacle, select_obstacles
from .profile import ProfileGeometry, validate_profile
from .synthesis import cascade_loss_db


@dataclass(frozen=True)
class ObstacleContribution:
    """单个被选中障碍对外汇报的一份明细。"""

    sample_index: int
    distance_m: float
    ground_elevation_m: float
    side: str
    depth: int
    segment_left_distance_m: float
    segment_right_distance_m: float
    d1_m: float
    d2_m: float
    h_m: float
    v: float
    loss_db: float


@dataclass(frozen=True)
class ProfileAssessment:
    """整条剖面的多刃评估结果。"""

    total_loss_db: float
    is_los: bool
    obstacle_count: int
    obstacles: tuple[ObstacleContribution, ...]
    wavelength_m: float
    path_length_m: float


def _to_contribution(obstacle: SelectedObstacle) -> ObstacleContribution:
    return ObstacleContribution(
        sample_index=obstacle.sample_index,
        distance_m=obstacle.distance_m,
        ground_elevation_m=obstacle.ground_elevation_m,
        side=obstacle.segment.side,
        depth=obstacle.segment.depth,
        segment_left_distance_m=obstacle.segment.left_distance_m,
        segment_right_distance_m=obstacle.segment.right_distance_m,
        d1_m=obstacle.segment.d1_m,
        d2_m=obstacle.segment.d2_m,
        h_m=obstacle.segment.h_m,
        v=obstacle.v,
        loss_db=obstacle.loss_db,
    )


def assess_profile_geometry(profile: ProfileGeometry) -> ProfileAssessment:
    """对已校验的剖面几何做多刃评估。"""
    selected = select_obstacles(profile)
    contributions = tuple(_to_contribution(o) for o in selected)
    return ProfileAssessment(
        total_loss_db=cascade_loss_db(selected),
        # 没有任何采样点位于全链路直视线之上（最大 v<0）时递归在根段
        # 即停止，selected 为空——这就是几何通视；擦边点 v=0 仍选中。
        is_los=len(selected) == 0,
        obstacle_count=len(contributions),
        obstacles=contributions,
        wavelength_m=wavelength_m(profile.frequency_mhz),
        path_length_m=profile.path_length_m,
    )


def assess_profile(
    frequency_mhz: float,
    path_length_m: float,
    tx_ground_elevation_m: float,
    tx_antenna_height_m: float,
    rx_ground_elevation_m: float,
    rx_antenna_height_m: float,
    profile_samples: Sequence[tuple[float, float]],
) -> ProfileAssessment:
    """从原始剖面参数出发：校验 → 选障碍 → 合成。"""
    profile = validate_profile(
        frequency_mhz=frequency_mhz,
        path_length_m=path_length_m,
        tx_ground_elevation_m=tx_ground_elevation_m,
        tx_antenna_height_m=tx_antenna_height_m,
        rx_ground_elevation_m=rx_ground_elevation_m,
        rx_antenna_height_m=rx_antenna_height_m,
        profile_samples=profile_samples,
    )
    return assess_profile_geometry(profile)

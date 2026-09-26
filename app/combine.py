"""多刃损耗的合成。

级联方法（Deygout 合成）：每个被摊出的障碍先用现有单刃内核
knife_edge_loss_db 算出自己的那份附加损耗，再按 dB 直接相加，
得到全链路的总附加损耗。

没有任何障碍被摊出（全程通视）时为空和，即 0 dB——绝不因为地形
有起伏就凭空累加损耗。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from .loss import knife_edge_loss_db
from .multiedge import EdgeObstacle


@dataclass(frozen=True)
class CombinedLoss:
    """合成结果：总附加损耗 + 各障碍各自的那一份（与障碍列表一一对应）。"""

    total_db: float
    per_obstacle_db: tuple[float, ...]


def combine_edge_losses(obstacles: Sequence[EdgeObstacle]) -> CombinedLoss:
    """把各障碍的单刃损耗按 dB 合成为全链路总附加损耗。"""
    losses = tuple(knife_edge_loss_db(o.v) for o in obstacles)
    return CombinedLoss(total_db=math.fsum(losses), per_obstacle_db=losses)

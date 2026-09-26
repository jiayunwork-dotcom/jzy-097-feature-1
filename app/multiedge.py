"""主障碍的递归选取与分段（多刃串联的 Deygout 主障碍法）。

沿链路横亘多道山脊时，本模块负责把「真正参与绕射」的凸起逐层摊出。
采用业界处理串联多刃的标准手法之一——Deygout 主障碍递归选取：

1. 在当前子链路上，对每一个采样点，以该段子链路两端点的连线为
   参考直视线，折算其超出高度 h 与菲涅尔参数
       v = h·sqrt(2·(d1+d2)/(λ·d1·d2))，
   其中 d1、d2 是该点到本子链路两个端点（而不是全链路收发两端）
   的水平距离；
2. 取 v 最大的那个点作为本段子链路的主障碍。选择依据是菲涅尔参数
   v（几何遮挡严重程度），不是海拔最高、也不是离端点最近——在
   直视线倾斜时这三者并不重合；
3. 主障碍把本子链路切成左右两段子链路：左段端点为（左端天线顶/
   上一级山顶）与主障碍山顶，右段为（主障碍山顶，右端天线顶/
   上一级山顶）；分别以这两段新的参考直视线递归重复第 1、2 步；
4. 当一段子链路内没有任何采样点位于它自己的参考直视线之上
   （最大 v 严格小于 0）时，该段停止递归；擦边点 v=0 仍按遮挡
   处理，与单刃内核 v=0 约 6 dB、非通视的口径一致。

每一个被选中的障碍都直接复用单刃内核 fresnel_parameter 与
knife_edge_loss_db 计算它在「自己所在子链路」几何下的那一份附加
损耗；本模块不复制、不改写单刃算法。

退化性质：若整条剖面只有一处高出直视线的凸起，则只有全链路
（深度 0）会选中障碍，所选障碍的 d1、d2、h 与全链路直视线折算
结果和把该处凸起单独喂给单刃接口完全一致。

参考线在采样点之间一律按两端点连线线性处理；地形本身不插值，
候选点只有给定采样点。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Optional

from .fresnel import fresnel_parameter
from .geometry import LinkGeometry
from .loss import knife_edge_loss_db
from .profile import ProfileGeometry, reference_line_height_at

SideLabel = Literal["root", "tx_side", "rx_side"]


@dataclass(frozen=True)
class ObstacleSegment:
    """障碍被选出时所在的那段子链路几何描述。"""

    left_distance_m: float  # 子链路左端里程（发射端一侧）
    right_distance_m: float  # 子链路右端里程（接收端一侧）
    left_reference_height_m: float  # 左端参考点海拔（天线顶或上级山顶）
    right_reference_height_m: float  # 右端参考点海拔
    d1_m: float  # 障碍到子链路左端的水平距离
    d2_m: float  # 障碍到子链路右端的水平距离
    h_m: float  # 障碍山顶相对该段参考线的超出高度（遮挡为正）
    side: SideLabel  # 该段相对上一级主障碍的位置
    depth: int  # 递归深度：0 为全链路主障碍


@dataclass(frozen=True)
class SelectedObstacle:
    """一个被逐层选出、参与总损耗合成的刃形障碍。"""

    sample_index: int
    distance_m: float
    ground_elevation_m: float
    v: float
    loss_db: float
    segment: ObstacleSegment


@dataclass(frozen=True)
class _SegmentTask:
    """递归工作栈中的一段待处理子链路。"""

    left_distance_m: float
    left_reference_height_m: float
    right_distance_m: float
    right_reference_height_m: float
    lo_index: int  # 候选采样点区间（左闭右开）
    hi_index: int
    side: SideLabel
    depth: int


def _select_dominant(
    profile: ProfileGeometry, task: _SegmentTask
) -> Optional[tuple[int, float, float, float, float]]:
    """在一段子链路的候选采样点中找菲涅尔参数最大的凸起。

    返回 (sample_index, h, d1, d2, v)。选取口径与单刃内核一致：
    只有某点位于该段参考线上或高出它（最大 v ≥ 0，擦边也算遮挡，
    对应单刃 v=0 的约 6 dB、非通视）时才返回主障碍；所有点都严格
    低于参考线（最大 v < 0）时返回 None，该段为通视段。
    """
    best: Optional[tuple[int, float, float, float, float]] = None
    best_v = -math.inf
    for i in range(task.lo_index, task.hi_index):
        sample = profile.samples[i]
        line_height = reference_line_height_at(
            task.left_distance_m,
            task.left_reference_height_m,
            task.right_distance_m,
            task.right_reference_height_m,
            sample.distance_m,
        )
        h = sample.ground_elevation_m - line_height
        d1 = sample.distance_m - task.left_distance_m
        d2 = task.right_distance_m - sample.distance_m
        v = fresnel_parameter(
            LinkGeometry(d1_m=d1, d2_m=d2, h_m=h), profile.frequency_mhz
        )
        # 里程严格递增，等 v（含多个擦边点）时保留最先出现的一个，
        # 选取结果确定。
        if v > best_v:
            best_v = v
            best = (i, h, d1, d2, v)
    if best is None or best_v < 0.0:
        return None
    return best


def select_obstacles(profile: ProfileGeometry) -> list[SelectedObstacle]:
    """按 Deygout 主障碍递归法逐层选出全部参与绕射的障碍。

    返回顺序为前序：全链路主障碍（depth 0）在前，其后是发射端一侧
    递归展开出的次级障碍，再是接收端一侧；每一级同理。
    """
    root = _SegmentTask(
        left_distance_m=0.0,
        left_reference_height_m=profile.tx_antenna_elevation_m,
        right_distance_m=profile.path_length_m,
        right_reference_height_m=profile.rx_antenna_elevation_m,
        lo_index=0,
        hi_index=len(profile.samples),
        side="root",
        depth=0,
    )
    stack: list[_SegmentTask] = [root]
    selected: list[SelectedObstacle] = []

    while stack:
        task = stack.pop()
        if task.hi_index <= task.lo_index:
            continue
        dominant = _select_dominant(profile, task)
        if dominant is None:
            continue
        idx, h, d1, d2, v = dominant
        sample = profile.samples[idx]
        selected.append(
            SelectedObstacle(
                sample_index=sample.index,
                distance_m=sample.distance_m,
                ground_elevation_m=sample.ground_elevation_m,
                v=v,
                loss_db=knife_edge_loss_db(v),
                segment=ObstacleSegment(
                    left_distance_m=task.left_distance_m,
                    right_distance_m=task.right_distance_m,
                    left_reference_height_m=task.left_reference_height_m,
                    right_reference_height_m=task.right_reference_height_m,
                    d1_m=d1,
                    d2_m=d2,
                    h_m=h,
                    side=task.side,
                    depth=task.depth,
                ),
            )
        )

        # 主障碍把本子链路切成两段：右段（主障碍山顶→右端）先压栈、
        # 左段（左端→主障碍山顶）后压栈，使左段先展开，输出呈前序。
        # 子段的端点参考海拔：天线顶端或上一级主障碍的山顶。
        # 直接挂在全链路主障碍下的左/右段标 tx_side/rx_side，更深的
        # 后代沿用其父段所在侧。
        left_side: SideLabel = "tx_side" if task.side == "root" else task.side
        right_side: SideLabel = "rx_side" if task.side == "root" else task.side
        stack.append(
            _SegmentTask(
                left_distance_m=sample.distance_m,
                left_reference_height_m=sample.ground_elevation_m,
                right_distance_m=task.right_distance_m,
                right_reference_height_m=task.right_reference_height_m,
                lo_index=idx + 1,
                hi_index=task.hi_index,
                side=right_side,
                depth=task.depth + 1,
            )
        )
        stack.append(
            _SegmentTask(
                left_distance_m=task.left_distance_m,
                left_reference_height_m=task.left_reference_height_m,
                right_distance_m=sample.distance_m,
                right_reference_height_m=sample.ground_elevation_m,
                lo_index=task.lo_index,
                hi_index=idx,
                side=left_side,
                depth=task.depth + 1,
            )
        )

    return selected

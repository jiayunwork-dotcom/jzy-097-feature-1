"""多刃绕射损耗的合成。

把 multiedge 逐层选出的各刃分量合成成一条链路的总附加损耗。

合成方法沿用 Deygout 主障碍法的级联口径：总附加损耗等于每个被选
中刃形障碍在其所属子链路几何下、由单刃内核算出的那一份附加损耗
直接相加（dB 域求和）：

    L_total = Σ J(v_i)

这些 v_i 不是对同一条直视线重复折算的，而是每一级都以该段子链路
端点（天线顶/上一级山顶）连线为参考线、以该障碍到子链路两端的
距离算出的，因此求和具备逐级遮挡的几何依据；绝不是把所有凸起对
全链路直视线的损耗一股脑相加。

空选择（全程通视）的和按 0 dB 处理。
"""

from __future__ import annotations

from .multiedge import SelectedObstacle


def cascade_loss_db(obstacles: list[SelectedObstacle]) -> float:
    """把各刃分量在 dB 域直接相加，得到链路总附加损耗。"""
    total = 0.0
    for obstacle in obstacles:
        total += obstacle.loss_db
    return total

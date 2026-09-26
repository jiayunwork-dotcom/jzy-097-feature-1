"""主障碍的递归选取与分段（Deygout 级联多刃绕射的前半段）。

选取规则（逐层进行，直至没有凸起剩下）：
1. 在当前（子）链路上，以两端点的连线作为参考直视线——最初是收发两端
   天线顶的连线，之后是上一层障碍顶与该侧端点的连线；
2. 扫描段内所有采样点，只考虑高出参考线的点（h>0，即真正咬进该段直视
   线的凸起），用现有单刃内核 fresnel_parameter 计算各自的菲涅尔参数 v；
3. 取 v 最大者为本段主障碍——注意是菲涅尔参数最大，而不是海拔最高或
   里程最近：直视线倾斜时，高海拔点可能几乎贴着参考线（v 很小），而
   低海拔点可能深深咬进菲涅尔区；
4. 主障碍把本段切成左右两段子链路，其顶点成为两段子链路的新端点，
   对每段子链路重复上述过程。

每个被摊出的障碍只记录它在自己那段子链路里的几何（d1、d2、h）与 v，
损耗的合成见 combine.py。绝不能「把所有凸起相对全链路直视线的损耗
一股脑相加」：凸起是否参与绕射、以多大超出高度参与，取决于它所在
子链路的参考线——主障碍的参考线可能已经把某些凸起压在身下，它们
不再单独贡献损耗。

边界约定：恰好擦着参考线（h=0）的采样点不算咬进，不摊为障碍；
因此全程通视（所有点都在直视线下方）时摊不出任何障碍。

实现用显式栈而非递归，剖面点数上千时也不受递归深度限制。
"""

from __future__ import annotations

from dataclasses import dataclass

from .fresnel import fresnel_parameter
from .geometry import LinkGeometry
from .profile import TerrainProfile, excess_height_m


@dataclass(frozen=True)
class EdgeObstacle:
    """被摊出的一个绕射障碍，几何量全部相对它所在的子链路。"""

    sample_index: int  # 对应剖面 points 的下标
    distance_m: float  # 里程（到发射端的水平距离），m
    depth: int  # 选取层深：0 为全链路主障碍，1 为其次级，依此类推
    d1_m: float  # 子链路内到左端点的水平距离，m
    d2_m: float  # 子链路内到右端点的水平距离，m
    h_m: float  # 相对子链路参考直视线的超出高度，m（>0）
    v: float  # 子链路几何下的菲涅尔参数


def find_obstacles(profile: TerrainProfile, frequency_mhz: float) -> list[EdgeObstacle]:
    """在整条剖面上逐层摊出所有参与绕射的障碍，按里程升序返回。"""
    xs = [p.distance_m for p in profile.points]
    zs = [p.elevation_m for p in profile.points]
    obstacles: list[EdgeObstacle] = []
    # 栈元素：(左端里程, 左端高度, 右端里程, 右端高度, 采样点下标lo, 下标hi, 层深)
    stack = [
        (
            0.0,
            profile.tx_top_m,
            profile.path_length_m,
            profile.rx_top_m,
            0,
            len(xs) - 1,
            0,
        )
    ]
    while stack:
        x_a, z_a, x_b, z_b, lo, hi, depth = stack.pop()
        if lo > hi:
            continue
        best_idx = -1
        best_v = 0.0  # 只摊出高出参考线的凸起（h>0 即 v>0）
        best_h = 0.0
        for i in range(lo, hi + 1):
            h = excess_height_m(xs[i], zs[i], x_a, z_a, x_b, z_b)
            if h <= 0.0:
                continue
            v = fresnel_parameter(
                LinkGeometry(d1_m=xs[i] - x_a, d2_m=x_b - xs[i], h_m=h),
                frequency_mhz,
            )
            if v > best_v:
                best_idx, best_v, best_h = i, v, h
        if best_idx < 0:
            continue
        x_m, z_m = xs[best_idx], zs[best_idx]
        obstacles.append(
            EdgeObstacle(
                sample_index=best_idx,
                distance_m=x_m,
                depth=depth,
                d1_m=x_m - x_a,
                d2_m=x_b - x_m,
                h_m=best_h,
                v=best_v,
            )
        )
        # 主障碍顶成为左右两段子链路的新端点
        stack.append((x_a, z_a, x_m, z_m, lo, best_idx - 1, depth + 1))
        stack.append((x_m, z_m, x_b, z_b, best_idx + 1, hi, depth + 1))
    obstacles.sort(key=lambda o: o.distance_m)
    return obstacles

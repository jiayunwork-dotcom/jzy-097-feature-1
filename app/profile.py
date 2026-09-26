"""地形剖面的表示与余隙折算。

多刃绕射评估的输入不再是一组预折算好的标量，而是沿链路按里程排列的
地形剖面：一串采样点，每个点给到发射端的水平距离与该点的地面海拔，
另加收发两端天线的架设高度与所在地海拔。

约定（钉死）：
- 收发直视线（参考线）由两端天线顶的连线确定，
  天线顶海拔 = 所在地海拔 + 架设高度；
- 每个采样点的「障碍顶」就是该点的地面海拔本身；剖面点之间不做地形
  插值，只在给到的采样点上判断；
- 采样点相对某条参考线的超出高度 h = 采样点海拔 − 参考线在该里程处的
  高度：h>0 表示咬进参考线（遮挡方向），h<0 表示有余隙；
- 参考线本身是两个端点之间的直线，可在任意里程处取值。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProfilePoint:
    """剖面采样点：里程 + 地面海拔。"""

    distance_m: float  # 到发射端的水平距离，m
    elevation_m: float  # 该点地面海拔，m


@dataclass(frozen=True)
class TerrainProfile:
    """整条链路的地形剖面与两端天线顶高度。"""

    path_length_m: float  # 收发间水平总距离，m
    tx_top_m: float  # 发射端天线顶海拔 = 所在地海拔 + 架设高度
    rx_top_m: float  # 接收端天线顶海拔
    points: tuple[ProfilePoint, ...]  # 按里程严格递增，全部落在收发之间


def reference_height_m(
    x_a_m: float, z_a_m: float, x_b_m: float, z_b_m: float, x_m: float
) -> float:
    """端点 (x_a, z_a) 与 (x_b, z_b) 连成的参考线在里程 x 处的高度。

    参考线是直线，与地形采样无关；地形只在采样点处取值，不做插值。
    """
    return z_a_m + (z_b_m - z_a_m) * (x_m - x_a_m) / (x_b_m - x_a_m)


def excess_height_m(
    distance_m: float,
    elevation_m: float,
    x_a_m: float,
    z_a_m: float,
    x_b_m: float,
    z_b_m: float,
) -> float:
    """采样点相对 (x_a,z_a)—(x_b,z_b) 参考线的超出高度：正为咬进，负为余隙。"""
    return elevation_m - reference_height_m(x_a_m, z_a_m, x_b_m, z_b_m, distance_m)

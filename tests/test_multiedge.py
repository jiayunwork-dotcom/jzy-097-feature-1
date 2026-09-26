"""多刃递归选取与合成的测试。

重点钉住四条：
1. 退化一致：单凸起剖面 ≡ 单刃接口；
2. 通视归零：所有点在直视线下方时总损耗为 0、判为通视；
3. 主障碍选的是菲涅尔参数 v 最大的凸起，而非海拔最高/距离最近；
4. 单调性：抬高任一凸起，合成总损耗不减。
另加级联分段几何、合成口径与规模测试。
"""

import math

from app.fresnel import fresnel_parameter
from app.geometry import LinkGeometry
from app.loss import knife_edge_loss_db
from app.multiedge import select_obstacles
from app.profile import validate_profile
from app.profile_service import assess_profile
from app.service import assess_full
from app.synthesis import cascade_loss_db


def build(
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


# ---------------------------------------------------------------------------
# 1) 退化一致性：单凸起剖面 ≡ 单刃接口
# ---------------------------------------------------------------------------


def test_single_bump_matches_single_knife_edge_flat_los():
    """唯一凸起高出水平直视线，多刃结果必须与单刃接口逐位一致。"""
    d1, d2, h, freq = 3000.0, 4000.0, 8.0, 900.0
    filler = [(1000.0, -50.0), (d1, h), (5000.0, -40.0), (6500.0, -60.0)]
    result = assess_profile(freq, d1 + d2, 0.0, 0.0, 0.0, 0.0, filler)
    single = assess_full(d1, d2, h, freq)
    assert result.obstacle_count == 1
    obstacle = result.obstacles[0]
    assert obstacle.depth == 0
    assert obstacle.side == "root"
    assert math.isclose(obstacle.v, single.v, abs_tol=1e-12)
    assert math.isclose(obstacle.loss_db, single.loss_db, abs_tol=1e-12)
    assert math.isclose(result.total_loss_db, single.loss_db, abs_tol=1e-12)
    assert result.is_los is False


def test_single_bump_matches_single_knife_edge_slanted_los():
    """直视线倾斜、两端海拔/天线高度不同，退化仍须与单刃完全一致。"""
    length = 7000.0
    tx_ground, tx_h = 100.0, 20.0   # 天线顶 120
    rx_ground, rx_h = 50.0, 10.0    # 天线顶 60
    bump_x, bump_z = 3000.0, 110.0
    samples = [(1000.0, 40.0), (bump_x, bump_z), (5000.0, 30.0)]

    ztx, zrx = tx_ground + tx_h, rx_ground + rx_h
    los_h = ztx + (zrx - ztx) * bump_x / length
    h = bump_z - los_h
    single = assess_full(bump_x, length - bump_x, h, 900.0)

    result = assess_profile(
        900.0, length, tx_ground, tx_h, rx_ground, rx_h, samples
    )
    assert result.obstacle_count == 1
    obstacle = result.obstacles[0]
    assert math.isclose(obstacle.h_m, h, abs_tol=1e-12)
    assert math.isclose(obstacle.v, single.v, abs_tol=1e-12)
    assert math.isclose(result.total_loss_db, single.loss_db, abs_tol=1e-12)


def test_single_grazing_point_matches_single_knife_edge():
    """唯一采样点恰好擦着直视线（h=0, v=0）：与单刃口径一致，约 6 dB 非通视。"""
    single = assess_full(3000.0, 4000.0, 0.0, 900.0)
    result = assess_profile(
        900.0, 7000.0, 0.0, 0.0, 0.0, 0.0,
        [(1000.0, -40.0), (3000.0, 0.0), (6000.0, -40.0)],
    )
    assert result.obstacle_count == 1
    assert result.is_los is False
    assert result.obstacles[0].v == 0.0
    assert math.isclose(result.total_loss_db, single.loss_db, abs_tol=1e-12)
    assert 5.9 < result.total_loss_db < 6.2


def test_degenerate_v_and_geometry_use_full_link():
    """退化时障碍的 d1/d2/h 是全链路几何，而不是子段巧合值。"""
    result = assess_profile(
        900.0, 7000.0, 0.0, 20.0, 0.0, 10.0, [(3000.0, 25.0)]
    )
    o = result.obstacles[0]
    # LOS: 20 -> 10 over 7000; at 3000: 20 - 10*3/7 = 15.7143; h = 9.2857
    assert math.isclose(o.h_m, 25.0 - (20.0 - 10.0 * 3000.0 / 7000.0), abs_tol=1e-12)
    assert o.d1_m == 3000.0
    assert o.d2_m == 4000.0
    assert o.segment_left_distance_m == 0.0
    assert o.segment_right_distance_m == 7000.0


# ---------------------------------------------------------------------------
# 2) 通视归零
# ---------------------------------------------------------------------------


def test_all_points_below_los_gives_zero_loss_and_los():
    """所有采样点都在直视线下方：总损耗 0，判为通视，不选中任何障碍。"""
    result = assess_profile(
        900.0, 10000.0, 0.0, 30.0, 0.0, 30.0,
        [(1000.0, 5.0), (5000.0, 20.0), (9000.0, 5.0)],
    )
    assert result.total_loss_db == 0.0
    assert result.is_los is True
    assert result.obstacle_count == 0
    assert result.obstacles == ()


def test_terrain_can_undulate_without_loss_when_below_los():
    """地形起伏但全部低于直视线：绝不凭空累加损耗。"""
    samples = [(i * 1000.0, 25.0 + 3.0 * math.sin(i)) for i in range(1, 10)]
    result = assess_profile(900.0, 10000.0, 0.0, 50.0, 0.0, 50.0, samples)
    assert result.is_los is True
    assert result.total_loss_db == 0.0
    assert result.obstacle_count == 0


def test_empty_profile_is_clear_zero_loss():
    result = assess_profile(900.0, 100.0, 0.0, 0.0, 0.0, 0.0, [])
    assert result.is_los is True
    assert result.total_loss_db == 0.0


def test_subsegment_clearance_does_not_spawn_obstacles():
    """次级点若低于「天线顶→主障碍山顶」连线，不允许被当成次级障碍。"""
    # 主障碍在 5000, 高 50；x=2000 处高 8，高于全链路 LOS（0）但
    # 低于连线 Tx(0) -> 山顶(50)：line@2000=20，故不应在左子段选中。
    result = assess_profile(
        900.0, 10000.0, 0.0, 0.0, 0.0, 0.0,
        [(2000.0, 8.0), (5000.0, 50.0), (8000.0, 8.0)],
    )
    indices = {o.sample_index for o in result.obstacles}
    assert indices == {1}


# ---------------------------------------------------------------------------
# 3) 主障碍 = 菲涅尔参数最大者（不是海拔最高/距离最近）
# ---------------------------------------------------------------------------


def test_dominant_obstacle_is_max_v_not_highest_or_nearest():
    """倾斜直视线下：海拔最高点与距发射端最近点都不是 v 最大者。

    直视线 10 -> 110（线性上升）：
    - x=500,  z=26：最近、且不是最高；对全链路 v≈1.24
    - x=3000, z=80：v≈2.14（最大）-> 必须是全链路主障碍
    - x=9500, z=90：海拔最高，但在直视线下方（h<0）
    """
    length, freq = 10000.0, 900.0
    samples = [(500.0, 26.0), (3000.0, 80.0), (7000.0, 40.0), (9500.0, 90.0)]
    profile = build(samples, freq=freq, length=length, tx_h=10.0, rx_ground=100.0, rx_h=10.0)
    selected = select_obstacles(profile)

    root = selected[0]
    assert root.segment.depth == 0
    assert root.sample_index == 1  # x=3000，v 最大
    assert root.distance_m == 3000.0
    # 海拔最高的是 9500@90，距发射端最近的是 500@26，均不得为主障碍
    assert root.ground_elevation_m == 80.0

    # 显式核验各点对全链路直视线的 v，确认选择确由 v 决定
    lam = 299_792_458.0 / (freq * 1.0e6)
    vs = {}
    for i, (x, z) in enumerate(samples):
        los = 10.0 + 100.0 * x / length
        h = z - los
        if h > 0:
            vs[i] = fresnel_parameter(LinkGeometry(x, length - x, h), freq)
    assert max(vs, key=vs.get) == 1
    assert math.isclose(root.v, vs[1], rel_tol=1e-12)
    assert vs[1] > vs[0]


def test_root_selection_ignores_max_elevation_on_slope():
    """同一算例经评估层再钉一次：输出明细里 root 是 max-v 点。"""
    result = assess_profile(
        900.0, 10000.0, 0.0, 10.0, 100.0, 10.0,
        [(500.0, 26.0), (3000.0, 80.0), (7000.0, 40.0), (9500.0, 90.0)],
    )
    root = result.obstacles[0]
    assert root.depth == 0 and root.sample_index == 1
    # 近发射端点作为发射侧次级障碍出现，它的参考线是
    # Tx 天线顶(0,10) -> 主障碍山顶(3000,80)：line@500=10+70*500/3000=21.667
    tx_side = [o for o in result.obstacles if o.side == "tx_side"]
    assert len(tx_side) == 1
    assert tx_side[0].sample_index == 0
    assert tx_side[0].depth == 1
    assert math.isclose(
        tx_side[0].h_m, 26.0 - (10.0 + 70.0 * 500.0 / 3000.0), abs_tol=1e-12
    )
    assert tx_side[0].d1_m == 500.0
    assert tx_side[0].d2_m == 2500.0
    # 接收侧两点都在全链路 LOS 下方，不产生接收侧障碍
    assert all(o.side != "rx_side" for o in result.obstacles)


def test_equal_v_tie_selects_leftmost_deterministically():
    """对称剖面上两个等 v 凸起：确定地选取里程较小的一个。"""
    result = assess_profile(
        900.0, 10000.0, 0.0, 0.0, 0.0, 0.0,
        [(2000.0, 10.0), (8000.0, 10.0)],
    )
    assert result.obstacles[0].sample_index == 0


# ---------------------------------------------------------------------------
# 4) 单调性
# ---------------------------------------------------------------------------


def _two_bump_result(bump_a, bump_b):
    return assess_profile(
        900.0, 10000.0, 0.0, 0.0, 0.0, 0.0,
        [(1000.0, -50.0), (2000.0, bump_a), (5000.0, -50.0),
         (8000.0, bump_b), (9000.0, -50.0)],
    )


def test_raising_leaf_obstacle_does_not_decrease_total():
    """抬高次级叶凸起，级联总损耗不减，且主/次分段保持不变。

    左山脊 30 m 明显主导（root），右山脊是接收侧次级叶障碍；
    把右山脊从 10 m 抬到 13 m 仍不足以反超成为主障碍，只是纯粹
    抬高这片叶，其自身那份单刃损耗应当增大。
    """
    base = _two_bump_result(30.0, 10.0)
    raised = _two_bump_result(30.0, 13.0)
    assert base.obstacles[0].sample_index == raised.obstacles[0].sample_index == 1
    base_leaf = next(o for o in base.obstacles if o.side == "rx_side")
    raised_leaf = next(o for o in raised.obstacles if o.side == "rx_side")
    assert raised_leaf.loss_db > base_leaf.loss_db
    assert raised.total_loss_db > base.total_loss_db


def test_raising_a_bump_across_dominance_flip_still_non_decreasing():
    """即使抬高令主/次身份互换，总损耗也不得下降。"""
    base = _two_bump_result(10.0, 10.0).total_loss_db
    flipped = _two_bump_result(10.0, 12.0).total_loss_db
    assert flipped > base


def test_raising_root_obstacle_monotonic_over_sweep():
    """小幅连续抬高主凸起，合成总损耗单调不减。"""
    losses = [_two_bump_result(10.0 + 0.5 * k, 10.0).total_loss_db for k in range(6)]
    assert all(b >= a - 1e-12 for a, b in zip(losses, losses[1:]))


def test_raising_single_bump_strictly_increases_loss():
    losses = [
        assess_profile(900.0, 10000.0, 0.0, 0.0, 0.0, 0.0, [(4000.0, 5.0 + 2.0 * k)])
        for k in range(5)
    ]
    assert all(b.total_loss_db > a.total_loss_db for a, b in zip(losses, losses[1:]))


# ---------------------------------------------------------------------------
# 级联分段与合成口径
# ---------------------------------------------------------------------------


def test_two_bumps_each_scored_against_own_subsegment():
    """两个凸起：root 对全链路 LOS 折算；次级对「主障碍山顶->Rx」连线折算。

    对称位置的两个等高山脊，d1 较小的左侧山脊（x=2000）几何系数
    sqrt(1/d1+1/d2) 更大、v 更大，成为全链路主障碍；右侧（x=8000）
    成为接收侧次级障碍。
    """
    result = _two_bump_result(10.0, 10.0)
    assert result.obstacle_count == 2
    root, secondary = result.obstacles[0], result.obstacles[1]
    assert root.depth == 0 and root.sample_index == 1  # x=2000
    assert secondary.side == "rx_side" and secondary.depth == 1
    assert secondary.sample_index == 3  # x=8000
    # 次级凸起参考线：主障碍山顶(2000,10) -> Rx(10000,0)；line@8000=2.5 -> h=7.5
    assert math.isclose(secondary.h_m, 7.5, abs_tol=1e-12)
    assert secondary.d1_m == 6000.0
    assert secondary.d2_m == 2000.0
    expected_v = fresnel_parameter(
        LinkGeometry(6000.0, 2000.0, 7.5), 900.0
    )
    assert math.isclose(secondary.v, expected_v, rel_tol=1e-12)
    assert math.isclose(secondary.loss_db, knife_edge_loss_db(expected_v), abs_tol=1e-12)
    # root 仍按全链路几何折算
    assert root.d1_m == 2000.0 and root.d2_m == 8000.0
    assert math.isclose(root.h_m, 10.0, abs_tol=1e-12)


def test_total_loss_is_db_sum_of_components():
    """合成口径：总损耗 = 各刃单刃损耗直接相加（dB 域）。"""
    result = _two_bump_result(10.0, 10.0)
    assert math.isclose(
        result.total_loss_db,
        sum(o.loss_db for o in result.obstacles),
        abs_tol=1e-12,
    )


def test_cascade_loss_empty_is_zero():
    assert cascade_loss_db([]) == 0.0


def test_three_level_recursion_uses_nested_reference_lines():
    """三级递归：每一级都以上级山顶连线为参考，距离取子段内部距离。

    全链路主障碍 5000@60；其发射侧子段（Tx->主山顶）的次级主障碍
    3000@44（须高于连线 Tx(0,0)->(5000,60) 在 3000 处的 36 m）；
    更左子段（Tx->3000 山顶）的三级障碍 1500@24（须高于连线在
    1500 处的 22 m）。8000@10 低于「主山顶->Rx」连线（24 m），
    不应被选中。
    """
    samples = [(1500.0, 24.0), (3000.0, 44.0), (5000.0, 60.0), (8000.0, 10.0)]
    result = assess_profile(900.0, 10000.0, 0.0, 0.0, 0.0, 0.0, samples)
    by_depth = {o.depth: o for o in result.obstacles}
    assert set(by_depth) == {0, 1, 2}
    assert by_depth[0].sample_index == 2
    assert by_depth[1].sample_index == 1
    assert by_depth[2].sample_index == 0
    # 三级点参考线：Tx(0,0) -> 次级山顶(3000,44)；line@1500=22 -> h=2
    assert math.isclose(by_depth[2].h_m, 2.0, abs_tol=1e-12)
    assert by_depth[2].d1_m == 1500.0 and by_depth[2].d2_m == 1500.0
    assert by_depth[2].side == "tx_side"
    # 次级点参考线：Tx(0,0) -> 主山顶(5000,60)；line@3000=36 -> h=8
    assert math.isclose(by_depth[1].h_m, 8.0, abs_tol=1e-12)
    assert by_depth[1].d1_m == 3000.0 and by_depth[1].d2_m == 2000.0
    assert math.isclose(
        result.total_loss_db,
        sum(o.loss_db for o in result.obstacles),
        abs_tol=1e-12,
    )


def test_obstacle_report_fields_complete():
    result = _two_bump_result(10.0, 10.0)
    o = result.obstacles[0]
    for field in (
        "sample_index", "distance_m", "ground_elevation_m", "side", "depth",
        "segment_left_distance_m", "segment_right_distance_m",
        "d1_m", "d2_m", "h_m", "v", "loss_db",
    ):
        assert hasattr(o, field)


# ---------------------------------------------------------------------------
# 规模
# ---------------------------------------------------------------------------


def test_handles_over_one_thousand_samples():
    n = 1500
    samples = [
        (10.0 + i * (9980.0 / (n - 1)), 15.0 if i % 137 == 0 else -30.0)
        for i in range(n)
    ]
    result = assess_profile(900.0, 10000.0, 0.0, 0.0, 0.0, 0.0, samples)
    assert result.obstacle_count >= 1
    assert result.total_loss_db > 0.0
    # 每个回报的 sample_index 都对应输入剖面里真实存在的采样点
    for o in result.obstacles:
        assert 0 <= o.sample_index < n
        assert o.d1_m > 0.0 and o.d2_m > 0.0


def test_worst_case_all_points_selected_completes():
    """凹形弧面（每点都在父弦之上）会选中全部点，验证可扩展与深度安全。"""
    n = 1000
    samples = []
    for i in range(1, n + 1):
        x = 5.0 + i * (9990.0 / (n + 1))
        samples.append((x, 0.0002 * x * (10000.0 - x)))
    result = assess_profile(900.0, 10000.0, 0.0, 0.0, 0.0, 0.0, samples)
    assert result.obstacle_count == n
    assert result.is_los is False
    depths = {o.depth for o in result.obstacles}
    assert max(depths) > 1  # 确实递归到了很深的层级（显式栈，不触顶）

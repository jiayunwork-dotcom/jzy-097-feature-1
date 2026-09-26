"""多刃绕射：主障碍递归选取、分段几何与级联合成的关键性质测试。

钉住四条几何与数值关系：
1. 退化一致：单凸起剖面 ≡ 该凸起单独喂单刃接口；
2. 通视归零：所有采样点都在直视线下方时总损耗为零、判为通视；
3. 主障碍选取：选菲涅尔参数最大的凸起，而不是海拔最高或里程最近的；
4. 单调性：只把某一处凸起继续抬高，合成后的总损耗不减。
"""

import math

from app.combine import combine_edge_losses
from app.fresnel import fresnel_parameter
from app.geometry import LinkGeometry
from app.loss import knife_edge_loss_db
from app.multiedge import find_obstacles
from app.profile_service import assess_profile
from app.profile_validation import validate_terrain_profile
from app.service import assess_full

FREQ = 900.0

# 退化算例：只有 4000 m 处一处凸起高出直视线（h=5），其余点都在直视线下方
DEGEN = dict(
    path_length_m=8000.0,
    tx_antenna_height_m=20.0,
    tx_site_elevation_m=100.0,
    rx_antenna_height_m=30.0,
    rx_site_elevation_m=150.0,
    frequency_mhz=FREQ,
    points=[(2000.0, 110.0), (4000.0, 155.0), (6000.0, 140.0)],
)

# 主障碍选取算例：直视线倾斜（收发高差 200 m）。
# 9500 m 处采样点海拔最高（201 m）且离接收端最近（500 m），但只高出直视
# 线 1 m；5000 m 处凸起海拔低得多，却高出直视线 20 m，菲涅尔参数最大。
SELECT = dict(
    path_length_m=10000.0,
    tx_antenna_height_m=10.0,
    tx_site_elevation_m=0.0,
    rx_antenna_height_m=10.0,
    rx_site_elevation_m=200.0,
    frequency_mhz=FREQ,
    points=[(2000.0, 60.0), (5000.0, 130.0), (9500.0, 201.0)],
)


def test_single_bulge_profile_degenerates_to_single_edge():
    """退化一致：单凸起剖面的总损耗 = 该凸起单独喂单刃接口的损耗。"""
    a = assess_profile(**DEGEN)
    solo = assess_full(d1_m=4000.0, d2_m=4000.0, h_m=5.0, frequency_mhz=FREQ)
    assert len(a.obstacles) == 1
    ob = a.obstacles[0]
    assert ob.sample_index == 1
    assert ob.distance_m == 4000.0
    assert ob.depth == 0
    assert ob.d1_m == 4000.0 and ob.d2_m == 4000.0
    assert math.isclose(ob.h_m, 5.0, rel_tol=1e-12)
    assert math.isclose(ob.v, solo.v, rel_tol=1e-9)
    assert math.isclose(a.total_loss_db, solo.loss_db, rel_tol=1e-9)
    assert math.isclose(ob.loss_db, solo.loss_db, rel_tol=1e-9)
    assert a.is_los is False
    assert solo.loss_db > 6.0  # 算例本身确实有可观损耗，不是空转


def test_all_points_below_los_give_zero_loss_and_los():
    """通视归零：地形起伏但全部在直视线下方，总损耗为零、判为通视。"""
    points = [
        (1000.0, 120.0),
        (2000.0, 110.0),
        (3000.0, 130.0),
        (4000.0, 120.0),
        (5000.0, 140.0),
        (6000.0, 130.0),
        (7000.0, 150.0),
    ]
    a = assess_profile(**{**DEGEN, "points": points})
    assert a.obstacles == ()
    assert a.total_loss_db == 0.0
    assert a.is_los is True


def test_empty_profile_gives_zero_loss_and_los():
    a = assess_profile(**{**DEGEN, "points": []})
    assert a.obstacles == ()
    assert a.total_loss_db == 0.0
    assert a.is_los is True


def test_combine_empty_obstacles_is_zero_db():
    combined = combine_edge_losses([])
    assert combined.total_db == 0.0
    assert combined.per_obstacle_db == ()


def test_main_obstacle_is_max_fresnel_parameter_not_highest_or_nearest():
    """主障碍 = 菲涅尔参数最大的凸起，而非海拔最高或离端点最近的。"""
    a = assess_profile(**SELECT)
    mains = [o for o in a.obstacles if o.depth == 0]
    assert len(mains) == 1
    main = mains[0]
    # 海拔最高（201 m）且离接收端最近（500 m）的是 9500 m 处采样点，
    # 但它只高出直视线 1 m；主障碍必须是 5000 m 处的凸起
    assert main.distance_m == 5000.0
    assert main.sample_index == 1
    expected_v = fresnel_parameter(LinkGeometry(5000.0, 5000.0, 20.0), FREQ)
    assert math.isclose(main.v, expected_v, rel_tol=1e-9)
    # 9500 处点被主障碍顶的参考线压住（相对子链路 h<0），不参与合成
    assert {o.distance_m for o in a.obstacles} == {2000.0, 5000.0}


def test_secondary_obstacle_uses_its_own_sub_link_geometry():
    """次级障碍的距离与参考线取自它所在的子链路，不是全链路。"""
    a = assess_profile(**SELECT)
    sec = next(o for o in a.obstacles if o.distance_m == 2000.0)
    assert sec.depth == 1
    # 子链路为 发射端(0,10)—主障碍顶(5000,130)：2000 m 处参考线高 58 m
    assert sec.d1_m == 2000.0 and sec.d2_m == 3000.0
    assert math.isclose(sec.h_m, 2.0, rel_tol=1e-12)
    expected_v = fresnel_parameter(LinkGeometry(2000.0, 3000.0, 2.0), FREQ)
    assert math.isclose(sec.v, expected_v, rel_tol=1e-9)
    # 级联合成：总损耗 = 各刃损耗的 dB 和
    main = next(o for o in a.obstacles if o.depth == 0)
    expected_total = knife_edge_loss_db(main.v) + knife_edge_loss_db(sec.v)
    assert math.isclose(a.total_loss_db, expected_total, rel_tol=1e-12)
    assert math.isclose(
        a.total_loss_db, math.fsum(o.loss_db for o in a.obstacles), rel_tol=1e-12
    )


def _three_hill_points():
    """三座互不重叠的三角形山脊，峰顶分别在 7.5/15/22.5 km。"""

    def elev(x):
        e = 60.0
        e += 70.0 * max(0.0, 1.0 - abs(x - 7500.0) / 3000.0)
        e += 80.0 * max(0.0, 1.0 - abs(x - 15000.0) / 4000.0)
        e += 65.0 * max(0.0, 1.0 - abs(x - 22500.0) / 3000.0)
        return e

    return [(float(x), elev(float(x))) for x in range(500, 30000, 500)]


def test_three_hills_recursion_and_composition():
    """三座山脊：中间最高的为主障碍，两侧各摊出一处次级障碍。"""
    a = assess_profile(
        path_length_m=30000.0,
        tx_antenna_height_m=50.0,
        tx_site_elevation_m=50.0,
        rx_antenna_height_m=50.0,
        rx_site_elevation_m=50.0,
        frequency_mhz=FREQ,
        points=_three_hill_points(),
    )
    assert [o.distance_m for o in a.obstacles] == [7500.0, 15000.0, 22500.0]
    depth = {o.distance_m: o.depth for o in a.obstacles}
    assert depth[15000.0] == 0
    assert depth[7500.0] == 1 and depth[22500.0] == 1
    # 各障碍的几何都来自自己的子链路
    v_main = fresnel_parameter(LinkGeometry(15000.0, 15000.0, 40.0), FREQ)
    v_left = fresnel_parameter(LinkGeometry(7500.0, 7500.0, 10.0), FREQ)
    v_right = fresnel_parameter(LinkGeometry(7500.0, 7500.0, 5.0), FREQ)
    got = {o.distance_m: o.v for o in a.obstacles}
    assert math.isclose(got[15000.0], v_main, rel_tol=1e-9)
    assert math.isclose(got[7500.0], v_left, rel_tol=1e-9)
    assert math.isclose(got[22500.0], v_right, rel_tol=1e-9)
    expected_total = math.fsum(
        [knife_edge_loss_db(v_main), knife_edge_loss_db(v_left), knife_edge_loss_db(v_right)]
    )
    assert math.isclose(a.total_loss_db, expected_total, rel_tol=1e-12)
    assert a.total_loss_db > knife_edge_loss_db(v_main)  # 级联确实叠加
    assert a.is_los is False


def test_raising_lone_bulge_raises_total_loss_monotonically():
    """单调性（单凸起）：逐级抬高凸起，总损耗逐级上升且与单刃接口一致。"""
    totals = []
    for elevation in (152.0, 153.0, 154.0, 155.0, 156.0, 158.0, 160.0):
        points = [(2000.0, 110.0), (4000.0, elevation), (6000.0, 140.0)]
        a = assess_profile(**{**DEGEN, "points": points})
        solo = assess_full(4000.0, 4000.0, elevation - 150.0, FREQ)
        assert math.isclose(a.total_loss_db, solo.loss_db, rel_tol=1e-9)
        totals.append(a.total_loss_db)
    assert all(b > a for a, b in zip(totals, totals[1:]))


def test_raising_one_bulge_in_multi_obstacle_profile_does_not_decrease_total():
    """单调性（多凸起）：只抬高其中一处凸起，总损耗不减。"""
    totals = []
    for k in range(9):  # 2000 m 处凸起海拔 60.0 → 64.0，其余不动
        elevation = 60.0 + 0.5 * k
        points = [(2000.0, elevation), (5000.0, 130.0), (9500.0, 201.0)]
        a = assess_profile(**{**SELECT, "points": points})
        # 整个过程中选取保持稳定：5000 仍是主障碍，2000 仍是次级
        assert {o.distance_m for o in a.obstacles} == {2000.0, 5000.0}
        totals.append(a.total_loss_db)
    assert all(b >= a for a, b in zip(totals, totals[1:]))
    assert totals[-1] > totals[0]


def test_thousands_of_points_all_los_is_handled():
    """上千个采样点也撑得住：2000 点全程通视，一次扫描即归零。"""
    n = 2000
    points = [((i + 1) * 5.0, 100.0 + 30.0 * math.sin(i)) for i in range(n)]
    a = assess_profile(
        path_length_m=(n + 1) * 5.0,
        tx_antenna_height_m=50.0,
        tx_site_elevation_m=100.0,
        rx_antenna_height_m=50.0,
        rx_site_elevation_m=100.0,
        frequency_mhz=FREQ,
        points=points,
    )
    assert a.is_los is True
    assert a.total_loss_db == 0.0


def test_sawtooth_plateau_peaks_not_double_counted():
    """600 个等高锯齿峰都高出全链路直视线，但级联只摊出两端两处。

    选出最左、最右两峰后，它们之间的参考线是平的，中间各峰恰好压在
    参考线上（h=0，不算咬进），不再单独贡献损耗——这正是「按几何
    级联」与「把所有凸起一股脑相加」的分水岭。
    """
    n = 1200
    points = [((i + 1) * 8.0, 150.0 if i % 2 == 0 else 50.0) for i in range(n)]
    profile = validate_terrain_profile(
        path_length_m=(n + 1) * 8.0,
        tx_antenna_height_m=10.0,
        tx_site_elevation_m=90.0,
        rx_antenna_height_m=10.0,
        rx_site_elevation_m=90.0,
        points=points,
    )
    obstacles = find_obstacles(profile, FREQ)
    assert len(obstacles) == 2
    assert obstacles[0].depth == 0 and obstacles[1].depth == 1
    combined = combine_edge_losses(obstacles)
    naive = knife_edge_loss_db(
        fresnel_parameter(LinkGeometry(8.0, 9600.0, 50.0), FREQ)
    )
    # 总损耗是两处端峰之和，绝不是 600 个峰的累加
    assert combined.total_db < 2.0 * naive
    assert len(combined.per_obstacle_db) == 2


def test_thousands_of_nested_obstacles_handled_without_recursion_limit():
    """抛物线剖面：每个采样点都被层层摊出（上千层分段），显式栈不受
    递归深度限制，且合成份数与障碍数一致。"""
    n = 3000
    span = (n + 1) * 4.0
    points = [
        ((i + 1) * 4.0, 2000.0 * ((i + 1) * 4.0 / span) * (1.0 - (i + 1) * 4.0 / span))
        for i in range(n)
    ]
    profile = validate_terrain_profile(
        path_length_m=span,
        tx_antenna_height_m=0.0,
        tx_site_elevation_m=0.0,
        rx_antenna_height_m=0.0,
        rx_site_elevation_m=0.0,
        points=points,
    )
    obstacles = find_obstacles(profile, FREQ)
    # 凹形剖面上每个点都高出自己所在子链路的参考线，全部被摊出
    assert len(obstacles) == n
    assert max(o.depth for o in obstacles) >= 10
    combined = combine_edge_losses(obstacles)
    assert combined.total_db > 0.0
    assert len(combined.per_obstacle_db) == n
    assert math.isclose(
        combined.total_db, math.fsum(combined.per_obstacle_db), rel_tol=1e-12
    )

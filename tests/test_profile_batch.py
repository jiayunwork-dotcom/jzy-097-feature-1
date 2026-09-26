"""多刃剖面批量调度测试：各条独立、互不覆盖。"""

from app.profile_batch import ProfileBatchItem, evaluate_profile_batch
from app.profile_service import assess_profile

BASE = dict(
    path_length_m=8000.0,
    tx_antenna_height_m=20.0,
    tx_site_elevation_m=100.0,
    rx_antenna_height_m=30.0,
    rx_site_elevation_m=150.0,
    frequency_mhz=900.0,
)

BULGE = [(2000.0, 110.0), (4000.0, 155.0), (6000.0, 140.0)]
CLEAR = [(2000.0, 110.0), (4000.0, 120.0), (6000.0, 140.0)]


def _item(profile_id, points, **kw):
    return ProfileBatchItem(profile_id=profile_id, points=tuple(points), **{**BASE, **kw})


def test_batch_results_match_individual_evaluation():
    items = [_item("a", BULGE), _item("b", CLEAR), _item("c", BULGE, frequency_mhz=1800.0)]
    results = evaluate_profile_batch(items)
    assert [r.profile_id for r in results] == ["a", "b", "c"]
    assert all(r.ok for r in results)
    for item, r in zip(items, results):
        solo = assess_profile(
            item.path_length_m,
            item.tx_antenna_height_m,
            item.tx_site_elevation_m,
            item.rx_antenna_height_m,
            item.rx_site_elevation_m,
            item.frequency_mhz,
            item.points,
        )
        assert r.result == solo


def test_batch_isolates_invalid_profiles():
    """一条剖面不合法只影响自己，其他剖面照常出结果。"""
    bad_points = [(2000.0, 110.0), (2000.0, 120.0)]  # 里程不递增
    items = [_item("ok-1", BULGE), _item("bad", bad_points), _item("ok-2", CLEAR)]
    results = evaluate_profile_batch(items)
    assert [r.ok for r in results] == [True, False, True]
    bad = results[1]
    assert bad.profile_id == "bad"
    assert bad.error_reason and "points[1].distance_m" in bad.error_reason
    assert results[2].result is not None and results[2].result.total_loss_db == 0.0


def test_batch_does_not_leak_state_between_items():
    """相同剖面重复出现，结果一致，互不覆盖。"""
    items = [_item("x", BULGE), _item("y", BULGE)]
    results = evaluate_profile_batch(items)
    assert results[0].result == results[1].result
    assert results[0].profile_id != results[1].profile_id

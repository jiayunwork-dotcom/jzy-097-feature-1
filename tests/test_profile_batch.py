"""多刃批量调度的单元测试：逐条独立、错误隔离。"""

from app.profile_batch import ProfileBatchItem, evaluate_profile_batch
from app.profile_service import assess_profile

GOOD_SAMPLES = [(2000.0, 10.0), (8000.0, 10.0)]
CLEAR_SAMPLES = [(5000.0, 5.0)]


def _item(link_id, *, samples=GOOD_SAMPLES, **overrides):
    kwargs = dict(
        link_id=link_id,
        frequency_mhz=900.0,
        path_length_m=10000.0,
        tx_ground_elevation_m=0.0,
        tx_antenna_height_m=0.0,
        rx_ground_elevation_m=0.0,
        rx_antenna_height_m=0.0,
        profile_samples=samples,
    )
    kwargs.update(overrides)
    return ProfileBatchItem(**kwargs)


def test_batch_results_match_individual_evaluation():
    items = [_item("a"), _item("b"), _item("c")]
    results = evaluate_profile_batch(items)
    assert [r.link_id for r in results] == ["a", "b", "c"]
    assert all(r.ok for r in results)
    for item, r in zip(items, results):
        solo = assess_profile(
            item.frequency_mhz,
            item.path_length_m,
            item.tx_ground_elevation_m,
            item.tx_antenna_height_m,
            item.rx_ground_elevation_m,
            item.rx_antenna_height_m,
            item.profile_samples,
        )
        assert r.result.total_loss_db == solo.total_loss_db
        assert r.result.obstacle_count == solo.obstacle_count


def test_batch_isolates_invalid_profile():
    """一条剖面里程不合法只影响自己，其他剖面照常出结果。"""
    items = [
        _item("ok-1"),
        _item(
            "bad",
            samples=[(3000.0, 5.0), (2000.0, 5.0)],
        ),
        _item("ok-2", samples=CLEAR_SAMPLES, tx_antenna_height_m=50.0,
              rx_antenna_height_m=50.0),
    ]
    results = evaluate_profile_batch(items)
    assert [r.ok for r in results] == [True, False, True]
    bad = results[1]
    assert bad.link_id == "bad"
    assert bad.error_reason and "profile[1].distance_m" in bad.error_reason
    assert results[2].result is not None
    assert results[2].result.total_loss_db == 0.0
    assert results[2].result.is_los is True


def test_batch_isolates_bad_frequency_and_antenna():
    items = [
        _item("bad-freq", frequency_mhz=0.0),
        _item("bad-antenna", rx_antenna_height_m=-2.0),
        _item("ok"),
    ]
    results = evaluate_profile_batch(items)
    assert [r.ok for r in results] == [False, False, True]
    assert "frequency_mhz" in results[0].error_reason
    assert "rx_antenna_height_m" in results[1].error_reason


def test_batch_does_not_leak_state():
    results = evaluate_profile_batch([_item("x"), _item("y")])
    assert results[0].result == results[1].result
    assert results[0].link_id != results[1].link_id

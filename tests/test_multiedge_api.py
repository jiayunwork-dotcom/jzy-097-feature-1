"""多刃剖面 HTTP 接口测试。"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _payload(**overrides):
    payload = {
        "link_id": "profile-1",
        "frequency_mhz": 900.0,
        "path_length_m": 10000.0,
        "tx": {"ground_elevation_m": 0.0, "antenna_height_m": 0.0},
        "rx": {"ground_elevation_m": 0.0, "antenna_height_m": 0.0},
        "profile": [
            {"distance_m": 1000.0, "elevation_m": -50.0},
            {"distance_m": 2000.0, "elevation_m": 10.0},
            {"distance_m": 5000.0, "elevation_m": -50.0},
            {"distance_m": 8000.0, "elevation_m": 10.0},
            {"distance_m": 9000.0, "elevation_m": -50.0},
        ],
    }
    payload.update(overrides)
    return payload


def test_multiedge_assessment_two_obstacles_breakdown():
    r = client.post("/v1/multiedge/assessment", json=_payload())
    assert r.status_code == 200
    body = r.json()
    assert body["link_id"] == "profile-1"
    assert body["is_los"] is False
    assert body["obstacle_count"] == 2
    assert body["total_loss_db"] > 6.0
    # 总损耗等于各分量之和
    assert body["total_loss_db"] == sum(
        o["loss_db"] for o in body["obstacles"]
    )
    root = body["obstacles"][0]
    assert root["depth"] == 0 and root["side"] == "root"
    assert root["sample_index"] == 1
    assert root["distance_m"] == 2000.0
    assert root["segment"]["d1_m"] == 2000.0
    assert root["segment"]["d2_m"] == 8000.0
    secondary = body["obstacles"][1]
    assert secondary["side"] == "rx_side" and secondary["depth"] == 1
    assert secondary["sample_index"] == 3


def test_multiedge_clear_profile_zero_loss_and_los():
    r = client.post(
        "/v1/multiedge/assessment",
        json=_payload(
            link_id="clear",
            tx={"ground_elevation_m": 0.0, "antenna_height_m": 30.0},
            rx={"ground_elevation_m": 0.0, "antenna_height_m": 30.0},
            profile=[{"distance_m": 5000.0, "elevation_m": 5.0}],
        ),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total_loss_db"] == 0.0
    assert body["is_los"] is True
    assert body["obstacle_count"] == 0
    assert body["obstacles"] == []
    assert body["wavelength_m"] > 0.0


def test_multiedge_degenerate_matches_single_edge_endpoint():
    """接口级退化一致性：单凸起剖面与单刃 assessment 数值一致。"""
    d1, d2, h = 3000.0, 4000.0, 8.0
    single = client.post(
        "/v1/diffraction/assessment",
        json={"d1_m": d1, "d2_m": d2, "h_m": h, "frequency_mhz": 900.0},
    ).json()
    multi = client.post(
        "/v1/multiedge/assessment",
        json=_payload(
            link_id=None,
            path_length_m=d1 + d2,
            profile=[
                {"distance_m": 1000.0, "elevation_m": -40.0},
                {"distance_m": d1, "elevation_m": h},
                {"distance_m": 6000.0, "elevation_m": -40.0},
            ],
        ),
    ).json()
    assert multi["obstacle_count"] == 1
    obstacle = multi["obstacles"][0]
    assert abs(obstacle["v"] - single["v"]) < 1e-12
    assert abs(obstacle["loss_db"] - single["loss_db"]) < 1e-12
    assert abs(multi["total_loss_db"] - single["loss_db"]) < 1e-12


def test_multiedge_dominant_is_max_v():
    body = client.post(
        "/v1/multiedge/assessment",
        json=_payload(
            tx={"ground_elevation_m": 0.0, "antenna_height_m": 10.0},
            rx={"ground_elevation_m": 100.0, "antenna_height_m": 10.0},
            profile=[
                {"distance_m": 500.0, "elevation_m": 26.0},
                {"distance_m": 3000.0, "elevation_m": 80.0},
                {"distance_m": 7000.0, "elevation_m": 40.0},
                {"distance_m": 9500.0, "elevation_m": 90.0},
            ],
        ),
    ).json()
    root = body["obstacles"][0]
    assert root["sample_index"] == 1  # 不是海拔最高的 index3，也不是最近的 index0


def test_multiedge_rejects_non_increasing_mileage_with_reason():
    r = client.post(
        "/v1/multiedge/assessment",
        json=_payload(
            profile=[
                {"distance_m": 2000.0, "elevation_m": 5.0},
                {"distance_m": 2000.0, "elevation_m": 6.0},
            ]
        ),
    )
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["code"] == "INVALID_INPUT"
    assert "profile[1].distance_m" in err["reason"]


def test_multiedge_rejects_mileage_outside_link():
    r = client.post(
        "/v1/multiedge/assessment",
        json=_payload(profile=[{"distance_m": 10000.0, "elevation_m": 5.0}]),
    )
    assert r.status_code == 400
    assert "profile[0].distance_m" in r.json()["error"]["reason"]


def test_multiedge_rejects_negative_antenna_height():
    r = client.post(
        "/v1/multiedge/assessment",
        json=_payload(tx={"ground_elevation_m": 0.0, "antenna_height_m": -1.0}),
    )
    assert r.status_code == 400
    assert "tx_antenna_height_m" in r.json()["error"]["reason"]


def test_multiedge_rejects_non_positive_frequency():
    r = client.post(
        "/v1/multiedge/assessment", json=_payload(frequency_mhz=0.0)
    )
    assert r.status_code == 400
    assert "frequency_mhz" in r.json()["error"]["reason"]


def test_multiedge_rejects_non_numeric_sample():
    r = client.post(
        "/v1/multiedge/assessment",
        json=_payload(
            profile=[{"distance_m": "far", "elevation_m": 5.0}]
        ),
    )
    # Pydantic 类型错误走 422；语义校验（非有限数等）走 400
    assert r.status_code in (400, 422)


def test_multiedge_rejects_extra_fields():
    payload = _payload()
    payload["unexpected"] = 1
    r = client.post("/v1/multiedge/assessment", json=payload)
    assert r.status_code == 422


def test_multiedge_batch_independent_isolation():
    good = _payload(link_id="ok")
    bad_mileage = _payload(
        link_id="bad",
        profile=[{"distance_m": 3000.0, "elevation_m": 5.0},
                 {"distance_m": 2000.0, "elevation_m": 5.0}],
    )
    clear = _payload(
        link_id="clear",
        tx={"ground_elevation_m": 0.0, "antenna_height_m": 50.0},
        rx={"ground_elevation_m": 0.0, "antenna_height_m": 50.0},
    )
    r = client.post(
        "/v1/multiedge/batch", json={"links": [good, bad_mileage, clear]}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 3
    ok, bad, clr = body["results"]
    assert ok["ok"] and ok["result"]["obstacle_count"] == 2
    assert not bad["ok"] and "profile[1].distance_m" in bad["error"]["reason"]
    assert clr["ok"] and clr["result"]["total_loss_db"] == 0.0
    assert clr["result"]["is_los"] is True


def test_multiedge_batch_results_do_not_overwrite():
    r = client.post(
        "/v1/multiedge/batch",
        json={"links": [_payload(link_id="x"), _payload(link_id="y")]},
    )
    results = r.json()["results"]
    assert results[0]["link_id"] == "x"
    assert results[1]["link_id"] == "y"
    assert (
        results[0]["result"]["total_loss_db"]
        == results[1]["result"]["total_loss_db"]
    )


def test_large_profile_over_endpoint():
    n = 1200
    profile = [
        {"distance_m": 5.0 + i * (9990.0 / n),
         "elevation_m": 12.0 if i % 100 == 0 else -30.0}
        for i in range(1, n)
    ]
    r = client.post(
        "/v1/multiedge/assessment", json=_payload(profile=profile)
    )
    assert r.status_code == 200
    body = r.json()
    assert body["obstacle_count"] >= 1
    assert body["total_loss_db"] > 0.0


def test_legacy_endpoints_unchanged():
    """新增多刃路由后，旧接口对外行为不变。"""
    body = client.post(
        "/v1/diffraction/assessment",
        json={"d1_m": 3000.0, "d2_m": 4000.0, "h_m": 8.0, "frequency_mhz": 900.0},
    ).json()
    assert body["loss_db"] > 6.0 and body["is_los"] is False

"""多刃剖面 HTTP 接口测试。"""

import json
import math

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

BASE_PROFILE = {
    "path_length_m": 8000.0,
    "tx_antenna_height_m": 20.0,
    "tx_site_elevation_m": 100.0,
    "rx_antenna_height_m": 30.0,
    "rx_site_elevation_m": 150.0,
    "frequency_mhz": 900.0,
    "points": [
        {"distance_m": 2000.0, "elevation_m": 110.0},
        {"distance_m": 4000.0, "elevation_m": 155.0},
        {"distance_m": 6000.0, "elevation_m": 140.0},
    ],
}

# 直视线倾斜的剖面：海拔最高、离接收端最近的点（9500 m 处）不是主障碍
TILTED_PROFILE = dict(
    BASE_PROFILE,
    path_length_m=10000.0,
    tx_antenna_height_m=10.0,
    tx_site_elevation_m=0.0,
    rx_antenna_height_m=10.0,
    rx_site_elevation_m=200.0,
    points=[
        {"distance_m": 2000.0, "elevation_m": 60.0},
        {"distance_m": 5000.0, "elevation_m": 130.0},
        {"distance_m": 9500.0, "elevation_m": 201.0},
    ],
)


def test_profile_assessment_degenerates_to_single_edge_for_lone_bulge():
    """退化一致：单凸起剖面的总损耗与单刃接口一致。"""
    r = client.post("/v1/diffraction/profile/assessment", json=BASE_PROFILE)
    assert r.status_code == 200
    body = r.json()
    solo = client.post(
        "/v1/diffraction/assessment",
        json={"d1_m": 4000.0, "d2_m": 4000.0, "h_m": 5.0, "frequency_mhz": 900.0},
    ).json()
    assert math.isclose(body["total_loss_db"], solo["loss_db"], rel_tol=1e-9)
    assert body["is_los"] is False
    assert body["obstacle_count"] == 1
    ob = body["obstacles"][0]
    assert ob["sample_index"] == 1
    assert ob["distance_m"] == 4000.0
    assert ob["depth"] == 0
    assert math.isclose(ob["v"], solo["v"], rel_tol=1e-9)
    assert math.isclose(ob["loss_db"], body["total_loss_db"], rel_tol=1e-9)


def test_profile_all_below_los_zero_loss_and_los():
    """通视归零：所有点都在直视线下方时总损耗为零、判为通视。"""
    payload = dict(
        BASE_PROFILE,
        points=[
            {"distance_m": 2000.0, "elevation_m": 120.0},
            {"distance_m": 4000.0, "elevation_m": 130.0},
            {"distance_m": 6000.0, "elevation_m": 140.0},
        ],
    )
    body = client.post("/v1/diffraction/profile/assessment", json=payload).json()
    assert body["total_loss_db"] == 0.0
    assert body["is_los"] is True
    assert body["obstacle_count"] == 0
    assert body["obstacles"] == []


def test_profile_main_obstacle_and_breakdown_visible():
    """主障碍是菲涅尔参数最大的凸起；各障碍分摊之和等于总损耗。"""
    body = client.post("/v1/diffraction/profile/assessment", json=TILTED_PROFILE).json()
    assert body["obstacle_count"] == 2
    mains = [o for o in body["obstacles"] if o["depth"] == 0]
    assert len(mains) == 1
    # 海拔最高（201 m）、离接收端最近（500 m）的 9500 m 点不是主障碍
    assert mains[0]["distance_m"] == 5000.0
    assert {o["distance_m"] for o in body["obstacles"]} == {2000.0, 5000.0}
    assert math.isclose(
        sum(o["loss_db"] for o in body["obstacles"]),
        body["total_loss_db"],
        rel_tol=1e-12,
    )
    assert body["is_los"] is False


def test_profile_response_carries_ids_and_wavelength():
    payload = dict(BASE_PROFILE, profile_id="p-1")
    body = client.post("/v1/diffraction/profile/assessment", json=payload).json()
    assert body["profile_id"] == "p-1"
    assert body["path_length_m"] == 8000.0
    assert body["frequency_mhz"] == 900.0
    assert body["wavelength_m"] > 0.0


def test_profile_non_increasing_distances_rejected():
    payload = dict(
        BASE_PROFILE,
        points=[
            {"distance_m": 4000.0, "elevation_m": 155.0},
            {"distance_m": 2000.0, "elevation_m": 110.0},
        ],
    )
    r = client.post("/v1/diffraction/profile/assessment", json=payload)
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["code"] == "INVALID_INPUT"
    assert "points[1].distance_m" in err["reason"]


def test_profile_point_outside_path_rejected():
    payload = dict(
        BASE_PROFILE, points=[{"distance_m": 9000.0, "elevation_m": 100.0}]
    )
    r = client.post("/v1/diffraction/profile/assessment", json=payload)
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["code"] == "INVALID_INPUT"
    assert "points[0].distance_m" in err["reason"]


def test_profile_negative_antenna_height_rejected():
    r = client.post(
        "/v1/diffraction/profile/assessment",
        json=dict(BASE_PROFILE, tx_antenna_height_m=-1.0),
    )
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["code"] == "INVALID_INPUT"
    assert "tx_antenna_height_m" in err["reason"]


def test_profile_non_finite_elevation_rejected():
    # httpx 的 json= 拒绝序列化 NaN，改为直接 POST 原始 JSON 文本
    payload = dict(BASE_PROFILE)
    payload["points"] = [{"distance_m": 1000.0, "elevation_m": float("nan")}]
    r = client.post(
        "/v1/diffraction/profile/assessment",
        content=json.dumps(payload),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["code"] == "INVALID_INPUT"
    assert "points[0].elevation_m" in err["reason"]


def test_profile_non_positive_frequency_rejected():
    r = client.post(
        "/v1/diffraction/profile/assessment",
        json=dict(BASE_PROFILE, frequency_mhz=0.0),
    )
    assert r.status_code == 400
    assert "frequency_mhz" in r.json()["error"]["reason"]


def test_profile_batch_independent_results():
    good = dict(BASE_PROFILE, profile_id="ok-1")
    bad = dict(
        BASE_PROFILE,
        profile_id="bad",
        points=[
            {"distance_m": 2000.0, "elevation_m": 110.0},
            {"distance_m": 2000.0, "elevation_m": 120.0},
        ],
    )
    los = dict(
        BASE_PROFILE,
        profile_id="ok-2",
        points=[{"distance_m": 4000.0, "elevation_m": 100.0}],
    )
    r = client.post(
        "/v1/diffraction/profile/batch", json={"profiles": [good, bad, los]}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 3
    a, b, c = body["results"]
    assert a["profile_id"] == "ok-1"
    assert a["ok"] and a["result"]["total_loss_db"] > 6.0
    assert a["result"]["obstacle_count"] == 1
    assert b["profile_id"] == "bad"
    assert not b["ok"] and "points[1].distance_m" in b["error"]["reason"]
    assert c["profile_id"] == "ok-2"
    assert c["ok"] and c["result"]["total_loss_db"] == 0.0
    assert c["result"]["is_los"] is True


def test_profile_batch_matches_solo_calls():
    """批量结果与逐条单独调用一致，互不覆盖。"""
    p1 = dict(BASE_PROFILE, profile_id="s-1")
    p2 = dict(TILTED_PROFILE, profile_id="s-2")
    body = client.post(
        "/v1/diffraction/profile/batch", json={"profiles": [p1, p2]}
    ).json()
    solo1 = client.post("/v1/diffraction/profile/assessment", json=p1).json()
    solo2 = client.post("/v1/diffraction/profile/assessment", json=p2).json()
    assert body["results"][0]["result"] == solo1
    assert body["results"][1]["result"] == solo2

"""报表中心: 生成 / 预览 / 记录 / 导出, 以及与数据查询页的数字一致性."""
import pytest

from app.extensions import db
from app.models import Measurement, Report


def _entries_day(client, station_id, day, period="daily"):
    if period == "daily":
        entries = [
            {"pollutant": "PM25", "value": 60.0},
            {"pollutant": "PM10", "value": 90.0},
            {"pollutant": "SO2", "value": 900.0},
            {"pollutant": "NO2", "value": 40.0},
            {"pollutant": "CO", "value": 1.2},
            {"pollutant": "O3", "value": 100.0},
        ]
    else:
        entries = [
            {"pollutant": "PM25", "value": 60.0},
            {"pollutant": "SO2", "value": 900.0},
            {"pollutant": "CO", "value": 12.0},
        ]
    measured_at = "%s 00:00" % day if period == "daily" else "%s 10:00" % day
    client.post(
        "/api/measurements/entries",
        json={
            "station_id": station_id,
            "measured_at": measured_at,
            "period": period,
            "data_source": "device",
            "recorder": "测试员",
            "entries": entries,
        },
    )


@pytest.fixture
def seeded_days(client, station, second_station):
    """station: 09-01/09-02 daily + hourly; second_station: 09-01 daily."""
    _entries_day(client, station.id, "2026-09-01", "daily")
    _entries_day(client, station.id, "2026-09-02", "daily")
    _entries_day(client, station.id, "2026-09-01", "hourly")
    _entries_day(client, second_station.id, "2026-09-01", "daily")


# ---------------------------------------------------------------------------
# 数字一致性: 报表的每个统计量都与查询页接口结果对得上
# ---------------------------------------------------------------------------
def test_daily_report_numbers_match_query_endpoints(client, seeded_days):
    body = client.post(
        "/api/reports/",
        json={"report_type": "daily", "date": "2026-09-01", "generated_by": "张三"},
    ).get_json()
    content = body["content"]

    params = "period=daily&date_from=2026-09-01&date_to=2026-09-01"

    # 1) 查询页 summary: 总量 / 超标次数 / 超标率 / 站点数
    summary = client.get("/api/query/measurements?%s" % params).get_json()["summary"]
    overview = content["overview"]
    assert overview["total"] == summary["total"] == 12
    assert overview["exceeded_count"] == summary["exceeded_count"]
    assert overview["exceed_rate"] == summary["exceed_rate"]
    assert overview["station_count"] == summary["station_count"] == 2

    # 2) 查询页聚合统计 group_by=pollutant: 均值 / 极值 / 超标次数
    for metric in ("avg", "max", "min", "count"):
        stats = client.get(
            "/api/query/statistics?group_by=pollutant&metric=%s&%s" % (metric, params)
        ).get_json()
        agg = {item["key"]: item for item in stats["items"]}
        for factor in content["factors"]:
            key = factor["pollutant"]
            if metric == "avg":
                assert factor["avg_value"] == agg[key]["value"]
            elif metric == "max":
                assert factor["max_value"] == agg[key]["value"]
            elif metric == "min":
                assert factor["min_value"] == agg[key]["value"]
            elif metric == "count":
                assert factor["count"] == agg[key]["count"]
                assert factor["exceeded_count"] == agg[key]["exceeded_count"]

    # 3) 达标率 = (有效样本 - 超标) / 有效样本, 与逐行数据核对
    for factor in content["factors"]:
        rows = client.get(
            "/api/query/measurements?%s&pollutant=%s&page_size=200"
            % (params, factor["pollutant"])
        ).get_json()["items"]
        applicable = [r for r in rows if r["limit_value"] is not None]
        exceeded = [r for r in rows if r["is_exceeded"]]
        assert factor["applicable_count"] == len(applicable)
        assert factor["exceeded_count"] == len(exceeded)
        if applicable:
            expected = round((len(applicable) - len(exceeded)) / len(applicable), 4)
            assert factor["compliance_rate"] == expected

    # 4) 极值站点/时间: 与查询页原始记录一致
    so2 = next(f for f in content["factors"] if f["pollutant"] == "SO2")
    rows = client.get(
        "/api/query/measurements?%s&pollutant=SO2&sort=value&order=desc" % params
    ).get_json()["items"]
    assert so2["max_value"] == rows[0]["value"]
    assert so2["max_value_at"] == rows[0]["measured_at"]
    assert so2["max_station_code"] == rows[0]["station"]["code"]

    # 5) 首要污染物: SO2=900/150=6 倍, 为周期内最高
    assert content["primary_pollutant"]["pollutant"] == "SO2"
    assert content["primary_pollutant"]["max_ratio"] == 6.0
    assert overview["primary_pollutant"] == "SO₂"


def test_hourly_report_excludes_factors_without_limit(client, seeded_days):
    body = client.post(
        "/api/reports/",
        json={"report_type": "daily", "date": "2026-09-01", "period": "hourly"},
    ).get_json()
    content = body["content"]
    pm25 = next(f for f in content["factors"] if f["pollutant"] == "PM25")
    # PM2.5 无小时限值: 有均值/极值, 但不参与达标率分母
    assert pm25["count"] == 1
    assert pm25["avg_value"] == 60.0
    assert pm25["applicable_count"] == 0
    assert pm25["compliance_rate"] is None

    co = next(f for f in content["factors"] if f["pollutant"] == "CO")
    assert co["limit_value"] == 10.0
    assert co["exceeded_count"] == 1
    assert co["compliance_rate"] == 0.0

    # 总达标率只统计有限值的因子 (SO2 + CO), PM2.5 不计入
    assert content["overview"]["applicable_count"] == 2
    assert content["overview"]["exceeded_count"] == 2
    assert content["overview"]["compliance_rate"] == 0.0


def test_report_scoped_by_station_matches_query(client, seeded_days):
    options = client.get("/api/stations/options").get_json()["items"]
    station_id = next(item["id"] for item in options if item["code"] == "TEST-002")
    body = client.post(
        "/api/reports/",
        json={"report_type": "daily", "date": "2026-09-01", "station_id": station_id},
    ).get_json()
    assert body["content"]["overview"]["total"] == 6
    assert body["content"]["overview"]["station_count"] == 1
    summary = client.get(
        "/api/query/measurements?period=daily&date_from=2026-09-01&date_to=2026-09-01&station_id=%d"
        % station_id
    ).get_json()["summary"]
    assert body["content"]["overview"]["total"] == summary["total"]


def test_weekly_and_monthly_windows(client, seeded_days):
    # 2026-09-01(周二) 属于 2026-W36 (08-31 ~ 09-06)
    weekly = client.post(
        "/api/reports/", json={"report_type": "weekly", "date": "2026-09-01"}
    ).get_json()
    assert weekly["period_key"] == "2026-W36"
    assert weekly["content"]["period"]["start"].startswith("2026-08-31")
    assert weekly["content"]["period"]["end"].startswith("2026-09-06")
    # 窗口覆盖 09-01 与 09-02 两天
    assert weekly["content"]["overview"]["total"] == 18

    monthly = client.post(
        "/api/reports/", json={"report_type": "monthly", "date": "2026-09-15"}
    ).get_json()
    assert monthly["period_key"] == "2026-09"
    assert monthly["content"]["overview"]["total"] == 18

    # 周报数字与查询页 08-31~09-06 一致
    summary = client.get(
        "/api/query/measurements?period=daily&date_from=2026-08-31&date_to=2026-09-06"
    ).get_json()["summary"]
    assert weekly["content"]["overview"]["total"] == summary["total"]


# ---------------------------------------------------------------------------
# 生成记录: 去重 / 覆盖 / 列表 / 详情 / 删除
# ---------------------------------------------------------------------------
def test_duplicate_report_conflicts_then_overwrite(client, seeded_days):
    payload = {"report_type": "daily", "date": "2026-09-01"}
    first = client.post("/api/reports/", json=payload)
    assert first.status_code == 201
    assert first.get_json()["created"] is True

    dup = client.post("/api/reports/", json=payload)
    assert dup.status_code == 409

    overwrite = client.post("/api/reports/", json={**payload, "overwrite": True})
    assert overwrite.status_code == 200
    assert overwrite.get_json()["created"] is False
    assert overwrite.get_json()["id"] == first.get_json()["id"]

    listing = client.get("/api/reports/").get_json()
    assert listing["total"] == 1


def test_report_records_list_filter_and_detail(client, seeded_days):
    client.post("/api/reports/", json={"report_type": "daily", "date": "2026-09-01"})
    client.post("/api/reports/", json={"report_type": "weekly", "date": "2026-09-01"})

    daily_only = client.get("/api/reports/?report_type=daily").get_json()
    assert daily_only["total"] == 1
    assert daily_only["items"][0]["report_type"] == "daily"
    assert "content" not in daily_only["items"][0]  # 列表不带快照正文

    keyword = client.get("/api/reports/?keyword=W36").get_json()
    assert keyword["total"] == 1

    rid = daily_only["items"][0]["id"]
    detail = client.get("/api/reports/%d" % rid).get_json()
    assert detail["content"]["factors"]
    assert detail["report_no"].startswith("D")

    deleted = client.delete("/api/reports/%d" % rid)
    assert deleted.status_code == 200
    assert client.get("/api/reports/%d" % rid).status_code == 404


def test_preview_does_not_persist(client, seeded_days):
    resp = client.get("/api/reports/preview?report_type=daily&date=2026-09-01")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["content"]["overview"]["total"] == 12
    assert body["already_exists"] is False
    assert client.get("/api/reports/").get_json()["total"] == 0


def test_generate_empty_period_rejected(client, station):
    resp = client.post("/api/reports/", json={"report_type": "monthly", "date": "2026-01-01"})
    assert resp.status_code == 422
    assert resp.get_json()["error"]["fields"]["date"] == "no_data"


def test_invalid_report_params(client):
    assert client.get("/api/reports/preview?report_type=yearly").status_code == 422
    assert client.post("/api/reports/", json={"report_type": "daily", "date": "bad"}).status_code == 422
    assert client.post(
        "/api/reports/", json={"report_type": "daily", "station_id": 99999}
    ).status_code == 422
    assert client.get("/api/reports/?report_type=yearly").status_code == 422


# ---------------------------------------------------------------------------
# 导出: 读冻结快照, 且数字与快照一致
# ---------------------------------------------------------------------------
def test_export_csv_matches_frozen_snapshot(client, seeded_days):
    body = client.post(
        "/api/reports/", json={"report_type": "daily", "date": "2026-09-01"}
    ).get_json()
    content = body["content"]
    rid = body["id"]
    resp = client.get("/api/reports/%d/export" % rid)
    assert resp.status_code == 200
    assert "attachment" in resp.headers["Content-Disposition"]
    text = resp.get_data(as_text=True)
    assert text.startswith("﻿")

    # 导出中的关键数字与快照一致
    so2 = next(f for f in content["factors"] if f["pollutant"] == "SO2")
    lines = text.splitlines()
    so2_line = next(line for line in lines if line.startswith("SO₂"))
    cells = so2_line.split(",")
    assert float(cells[3]) == so2["avg_value"]
    assert float(cells[4]) == so2["max_value"]
    assert int(cells[10]) == so2["count"]
    assert int(cells[12]) == so2["exceeded_count"]

    # 标题/单号/首要污染物出现在导出中
    assert body["report_no"] in text
    assert "首要污染物" in text and "SO₂" in text


def test_snapshot_remains_frozen_after_data_change(client, app, seeded_days):
    body = client.post(
        "/api/reports/", json={"report_type": "daily", "date": "2026-09-01"}
    ).get_json()
    rid = body["id"]
    frozen_total = body["content"]["overview"]["total"]

    # 生成后补录当天数据 (不同时刻, 避免唯一约束冲突)
    options = client.get("/api/stations/options").get_json()["items"]
    station_id = next(item["id"] for item in options if item["code"] == "TEST-001")
    client.post(
        "/api/measurements/entries",
        json={
            "station_id": station_id,
            "measured_at": "2026-09-01 18:00",
            "period": "hourly",
            "data_source": "manual",
            "entries": [
                {"pollutant": "PM25", "value": 70.0},
                {"pollutant": "SO2", "value": 200.0},
            ],
        },
    )

    with app.app_context():
        assert Measurement.query.count() > frozen_total
        report = db.session.get(Report, rid)
        assert report.content["overview"]["total"] == frozen_total

    exported = client.get("/api/reports/%d/export" % rid).get_data(as_text=True)
    # 快照中的总量仍然是冻结值(12), 不随补录变化
    assert str(frozen_total) in exported


def test_options_payload(client):
    body = client.get("/api/reports/options").get_json()
    assert {item["value"] for item in body["report_types"]} == {"daily", "weekly", "monthly"}
    assert {item["value"] for item in body["pollutants"]} == {
        "PM25", "PM10", "SO2", "NO2", "CO", "O3"
    }

"""报表中心测试: 生成 / 记录留存 / 导出, 以及与数据查询页的数字对齐."""


def _seed_week(client, station, entry_payload):
    """2026-09-01(周二) ~ 2026-09-02(周三): daily 周期数据."""
    client.post(
        "/api/measurements/entries",
        json=entry_payload(
            station.id,
            measured_at="2026-09-01 00:00",
            period="daily",
            entries=[
                {"pollutant": "PM25", "value": 60.0},   # 达标 (<75)
                {"pollutant": "SO2", "value": 900.0},   # 超标 (>150)
                {"pollutant": "CO", "value": 2.0},      # 达标 (<4)
            ],
        ),
    )
    client.post(
        "/api/measurements/entries",
        json=entry_payload(
            station.id,
            measured_at="2026-09-02 00:00",
            period="daily",
            entries=[
                {"pollutant": "PM25", "value": 100.0},  # 超标 (>75)
                {"pollutant": "SO2", "value": 100.0},   # 达标
                {"pollutant": "CO", "value": 6.0},      # 超标 (>4)
            ],
        ),
    )


# ------------------------------------------------------------------ generation
def test_daily_report_factors_match_query_statistics(client, station, entry_payload):
    _seed_week(client, station, entry_payload)

    body = client.post(
        "/api/reports",
        json={"report_type": "daily", "period": "daily", "date": "2026-09-01"},
    ).get_json()

    factors = {row["pollutant"]: row for row in body["content"]["factors"]}

    # 与查询页 group_by=pollutant 的聚合结果逐一比对
    stats = client.get(
        "/api/query/statistics?group_by=pollutant&metric=avg"
        "&period=daily&date_from=2026-09-01&date_to=2026-09-01"
    ).get_json()
    stats_map = {item["key"]: item for item in stats["items"]}

    for code in ("PM25", "SO2", "CO"):
        assert factors[code]["avg_value"] == stats_map[code]["value"]
        assert factors[code]["sample_count"] == stats_map[code]["count"]
        assert factors[code]["exceeded_count"] == stats_map[code]["exceeded_count"]

    # 2026-09-01: PM25=60 均值/极值, SO2=900, CO=2
    assert factors["PM25"]["avg_value"] == 60.0
    assert factors["PM25"]["max_value"] == 60.0
    assert factors["PM25"]["min_value"] == 60.0
    assert factors["PM25"]["exceeded_count"] == 0
    assert factors["PM25"]["compliance_rate"] == 1.0
    assert factors["SO2"]["exceeded_count"] == 1
    assert factors["SO2"]["compliance_rate"] == 0.0
    assert factors["SO2"]["max_station"] == "TEST-001 测试监测点"
    assert factors["SO2"]["max_measured_at"].startswith("2026-09-01")


def test_report_overall_matches_query_summary(client, station, entry_payload):
    _seed_week(client, station, entry_payload)
    body = client.post(
        "/api/reports",
        json={"report_type": "weekly", "period": "daily", "date": "2026-09-01"},
    ).get_json()

    # 该周窗口 2026-08-31(周一) ~ 2026-09-06(周日)
    assert body["period_start"] == "2026-08-31"
    assert body["period_end"] == "2026-09-06"

    summary = client.get(
        "/api/query/measurements?period=daily&date_from=2026-08-31&date_to=2026-09-06"
    ).get_json()["summary"]

    overall = body["content"]["overall"]
    assert overall["sample_count"] == summary["total"] == 6
    assert overall["exceeded_count"] == summary["exceeded_count"] == 3
    assert overall["avg_value"] == summary["avg_value"]
    expected_exceed_rate = round(3 / 6, 4)
    assert overall["exceed_rate"] == summary["exceed_rate"] == expected_exceed_rate
    assert overall["compliance_rate"] == round(1 - expected_exceed_rate, 4) == 0.5


def test_primary_pollutant_picks_lowest_compliance(client, station, entry_payload):
    _seed_week(client, station, entry_payload)
    body = client.post(
        "/api/reports",
        json={"report_type": "weekly", "period": "daily", "date": "2026-09-01"},
    ).get_json()
    primary = body["content"]["primary_pollutant"]
    # PM25 / SO2 / CO 各超标 1 次, 样本均为 2, 超标率并列 0.5;
    # 按因子定义顺序 PM25 排在最前
    assert primary["pollutant"] == "PM25"
    assert primary["pollutant_label"] == "PM2.5"
    assert primary["exceeded_count"] == 1
    assert body["primary_pollutant"] == "PM25"


def test_no_primary_pollutant_when_all_compliant(client, station, entry_payload):
    client.post(
        "/api/measurements/entries",
        json=entry_payload(
            station.id,
            measured_at="2026-09-01 00:00",
            period="daily",
            entries=[{"pollutant": "PM25", "value": 30.0}, {"pollutant": "CO", "value": 1.0}],
        ),
    )
    body = client.post(
        "/api/reports",
        json={"report_type": "daily", "period": "daily", "date": "2026-09-01"},
    ).get_json()
    assert body["content"]["primary_pollutant"] is None
    assert body["primary_pollutant"] is None


def test_weekly_report_contains_daily_breakdown(client, station, entry_payload):
    _seed_week(client, station, entry_payload)
    body = client.post(
        "/api/reports",
        json={"report_type": "weekly", "period": "daily", "date": "2026-09-01"},
    ).get_json()
    breakdown = {day["date"]: day for day in body["content"]["daily_breakdown"]}
    assert set(breakdown) == {
        "2026-08-31",
        "2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-05", "2026-09-06",
    }
    day1 = breakdown["2026-09-01"]
    pm25 = next(item for item in day1["factors"] if item["pollutant"] == "PM25")
    assert pm25["avg_value"] == 60.0
    assert day1["sample_count"] == 3
    assert day1["exceeded_count"] == 1
    assert breakdown["2026-09-03"]["sample_count"] == 0


def test_monthly_report_window(client, station, entry_payload):
    client.post(
        "/api/measurements/entries",
        json=entry_payload(
            station.id,
            measured_at="2026-09-15 00:00",
            period="daily",
            entries=[{"pollutant": "PM25", "value": 50.0}],
        ),
    )
    body = client.post(
        "/api/reports",
        json={"report_type": "monthly", "period": "daily", "date": "2026-09-15"},
    ).get_json()
    assert body["period_start"] == "2026-09-01"
    assert body["period_end"] == "2026-09-30"
    assert body["period_label"] == "2026-09"
    assert body["content"]["factors"][0]["sample_count"] == 1
    assert len(body["content"]["daily_breakdown"]) == 30


def test_hourly_pm25_has_no_limit_and_excluded_from_primary(client, station, entry_payload):
    # PM2.5 小时值无限值: 即使数值很高也不算超标, 不参与首要污染物判定
    client.post(
        "/api/measurements/entries",
        json=entry_payload(
            station.id,
            measured_at="2026-09-01 10:00",
            period="hourly",
            entries=[{"pollutant": "PM25", "value": 500.0}, {"pollutant": "SO2", "value": 600.0}],
        ),
    )
    body = client.post(
        "/api/reports",
        json={"report_type": "daily", "period": "hourly", "date": "2026-09-01"},
    ).get_json()
    factors = {row["pollutant"]: row for row in body["content"]["factors"]}
    assert factors["PM25"]["limit_value"] is None
    assert factors["PM25"]["exceeded_count"] == 0
    # 与查询页 group_by=pollutant 口径一致: 无超限记录即超标率 0 / 达标率 100%
    stats = client.get(
        "/api/query/statistics?group_by=pollutant&period=hourly"
        "&date_from=2026-09-01&date_to=2026-09-01"
    ).get_json()
    pm25_stats = next(item for item in stats["items"] if item["key"] == "PM25")
    assert factors["PM25"]["exceed_rate"] == pm25_stats["exceed_rate"] == 0.0
    assert factors["PM25"]["compliance_rate"] == 1.0
    assert factors["SO2"]["limit_value"] == 500.0
    assert body["content"]["primary_pollutant"]["pollutant"] == "SO2"


# ------------------------------------------------------------------ validation
def test_report_rejects_empty_window(client, station):
    response = client.post(
        "/api/reports",
        json={"report_type": "daily", "period": "daily", "date": "2026-01-01"},
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["fields"]["date"] == "no_data"


def test_report_rejects_bad_type_and_period(client):
    assert client.post(
        "/api/reports", json={"report_type": "yearly", "period": "daily", "date": "2026-09-01"}
    ).status_code == 422
    assert client.post(
        "/api/reports", json={"report_type": "daily", "period": "weekly", "date": "2026-09-01"}
    ).status_code == 422
    assert client.post(
        "/api/reports", json={"report_type": "daily", "period": "daily"}
    ).status_code == 422


# ------------------------------------------------------------------ records
def test_report_records_list_detail_delete(client, station, entry_payload):
    _seed_week(client, station, entry_payload)
    created = client.post(
        "/api/reports",
        json={"report_type": "daily", "period": "daily", "date": "2026-09-01", "creator": "张工"},
    ).get_json()
    report_id = created["id"]

    listing = client.get("/api/reports").get_json()
    assert listing["total"] == 1
    row = listing["items"][0]
    assert row["id"] == report_id
    assert row["creator"] == "张工"
    assert row["total_count"] == 3
    assert "content" not in row  # 列表不携带快照正文

    # 类型筛选
    filtered = client.get("/api/reports?report_type=weekly").get_json()
    assert filtered["total"] == 0

    detail = client.get("/api/reports/%d" % report_id).get_json()
    assert detail["content"]["factors"]
    assert detail["title"].endswith("日报(全部监测点 · 日均值)") or "日报" in detail["title"]

    assert client.delete("/api/reports/%d" % report_id).status_code == 200
    assert client.get("/api/reports/%d" % report_id).status_code == 404
    assert client.get("/api/reports").get_json()["total"] == 0


def test_report_snapshot_is_immutable_when_data_changes(client, station, entry_payload):
    _seed_week(client, station, entry_payload)
    created = client.post(
        "/api/reports",
        json={"report_type": "daily", "period": "daily", "date": "2026-09-01"},
    ).get_json()
    assert created["total_count"] == 3

    # 之后新增同日数据, 已生成的报表快照不应改变
    client.post(
        "/api/measurements/entries",
        json=entry_payload(
            station.id,
            measured_at="2026-09-01 00:00",
            period="daily",
            entries=[{"pollutant": "NO2", "value": 50.0}],
            overwrite=True,
        ),
    )
    detail = client.get("/api/reports/%d" % created["id"]).get_json()
    assert detail["content"]["overall"]["sample_count"] == 3


# ------------------------------------------------------------------ export
def test_report_export_csv(client, station, entry_payload):
    _seed_week(client, station, entry_payload)
    created = client.post(
        "/api/reports",
        json={"report_type": "weekly", "period": "daily", "date": "2026-09-01"},
    ).get_json()
    response = client.get("/api/reports/%d/export" % created["id"])
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "周报" in text
    assert "首要污染物" in text
    assert "PM2.5" in text
    assert "逐日因子均值" in text
    # 超标率/达标率成对面值
    assert "50.0%" in text
    assert "50.0%" in text

    # 导出文件名带 attachment
    disposition = response.headers["Content-Disposition"]
    assert disposition.startswith("attachment; filename=monitoring_report_weekly_")


def test_report_options(client):
    body = client.get("/api/reports/options").get_json()
    assert {item["value"] for item in body["report_types"]} == {"daily", "weekly", "monthly"}
    assert {item["value"] for item in body["periods"]} == {"hourly", "daily"}


def test_report_respects_station_scope(client, station, second_station, entry_payload):
    _seed_week(client, station, entry_payload)
    client.post(
        "/api/measurements/entries",
        json=entry_payload(
            second_station.id,
            measured_at="2026-09-01 00:00",
            period="daily",
            entries=[{"pollutant": "PM25", "value": 30.0}],
        ),
    )
    body = client.post(
        "/api/reports",
        json={
            "report_type": "daily", "period": "daily", "date": "2026-09-01",
            "station_ids": [second_station.id],
        },
    ).get_json()
    assert body["content"]["overall"]["sample_count"] == 1
    factors = {row["pollutant"]: row for row in body["content"]["factors"]}
    assert factors["PM25"]["sample_count"] == 1
    assert factors["SO2"]["sample_count"] == 0
    # 与同样筛选条件的查询页统计对齐
    stats = client.get(
        "/api/query/statistics?group_by=pollutant&metric=count"
        "&station_id=%d&period=daily&date_from=2026-09-01&date_to=2026-09-01"
        % second_station.id
    ).get_json()
    assert stats["totals"]["count"] == 1

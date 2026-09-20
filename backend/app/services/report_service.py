"""监测报表生成: 日报 / 周报 / 月报.

报表中的每个数字都与"数据查询"页严格对齐:
- 过滤条件解析与结果集构造完全复用 query_service.parse_filters / apply_filters;
- 总数据量 / 超标次数 / 平均浓度直接取自 query_service.summary(即查询页顶部统计卡);
- 各因子聚合与查询页"聚合统计(group_by=pollutant)"使用相同的 SQL 表达式与舍入规则;
- 达标率 = 1 - 超标率, 超标率沿用查询页 round(exceeded / count, 4) 的口径。
"""
from datetime import datetime, time, timedelta

from sqlalchemy import cast, func, or_

from ..domain.constants import PERIOD_LABELS
from ..domain.standards import POLLUTANTS, POLLUTANT_CODES, get_limit, get_pollutant
from ..errors import NotFoundError, ValidationError
from ..extensions import db
from ..models import REPORT_TYPE_LABELS, Measurement, Report, Station
from ..models.base import iso, iso_date
from ..utils.validation import parse_date
from . import query_service

REPORT_TYPE_CHOICES = ("daily", "weekly", "monthly")


# ---------------------------------------------------------------- period window
def resolve_window(report_type, day):
    """Return [start_date, end_date] (inclusive) for the report type and anchor day.

    周报按自然周统计, 周一为一周的开始(与国内空气质量周报惯例一致)。
    """
    if report_type == "daily":
        return day, day
    if report_type == "weekly":
        start = day - timedelta(days=day.weekday())  # Monday
        return start, start + timedelta(days=6)
    if report_type == "monthly":
        start = day.replace(day=1)
        if start.month == 12:
            next_month = start.replace(year=start.year + 1, month=1)
        else:
            next_month = start.replace(month=start.month + 1)
        return start, next_month - timedelta(days=1)
    raise ValidationError(
        "报表类型仅支持: %s" % ", ".join(REPORT_TYPE_CHOICES), fields={"report_type": "unknown"}
    )


def period_label(report_type, start, end):
    if report_type == "daily":
        return start.isoformat()
    if report_type == "weekly":
        iso_year, iso_week, _ = start.isocalendar()
        return "%04d年第%02d周(%s~%s)" % (iso_year, iso_week, start.isoformat(), end.isoformat())
    return "%04d-%02d" % (start.year, start.month)


def _bounded_filters(base_filters, start, end):
    filters = dict(base_filters)
    filters["date_from"] = datetime.combine(start, time.min)
    filters["date_to"] = datetime.combine(end, time.max)
    return filters


# ---------------------------------------------------------------- aggregation
def _round2(value):
    """与 query_service.statistics 保持一致: avg/max/min 保留 2 位小数."""
    return round(float(value), 2) if value is not None else None


def aggregate_pollutants(filters):
    """Per-pollutant stats using the *same* SQL expressions as the query page."""
    rows = (
        query_service.apply_filters(
            db.session.query(
                Measurement.pollutant.label("pollutant"),
                func.avg(Measurement.value).label("avg_value"),
                func.max(Measurement.value).label("max_value"),
                func.min(Measurement.value).label("min_value"),
                func.count(Measurement.id).label("row_count"),
                func.sum(cast(Measurement.is_exceeded, db.Integer)).label("exceeded_count"),
            ),
            filters,
        )
        .group_by(Measurement.pollutant)
        .all()
    )
    return {row.pollutant: row for row in rows}


def _extremum_at(filters, pollutant, column, value):
    """measured_at / station label at which the extreme value occurs."""
    if value is None:
        return None, None
    row = (
        query_service.apply_filters(
            db.session.query(Measurement.measured_at, Station.code, Station.name)
            .filter(Measurement.pollutant == pollutant)
            .filter(column == value),
            filters,
        )
        .order_by(Measurement.measured_at.asc(), Measurement.id.asc())
        .first()
    )
    if row is None:
        return None, None
    station = "%s %s" % (row[1], row[2]) if row[1] else None
    return iso(row[0]), station


def build_pollutant_rows(filters):
    """Factor table rows, ordered by the canonical pollutant list."""
    agg = aggregate_pollutants(filters)
    rows = []
    for code in POLLUTANT_CODES:
        meta = get_pollutant(code)
        row = agg.get(code)
        if row is None:
            count = exceeded = 0
            avg = max_value = min_value = None
        else:
            count = int(row.row_count or 0)
            exceeded = int(row.exceeded_count or 0)
            avg = _round2(row.avg_value)
            max_value = _round2(row.max_value)
            min_value = _round2(row.min_value)

        max_at, max_station = _extremum_at(filters, code, Measurement.value, row.max_value if row else None)
        min_at, min_station = _extremum_at(filters, code, Measurement.value, row.min_value if row else None)

        # 与查询页超标率同口径; 达标率 = 1 - 超标率
        exceed_rate = round(exceeded / count, 4) if count else None
        limit = get_limit(code, filters.get("periods")[0] if filters.get("periods") else None)
        rows.append(
            {
                "pollutant": code,
                "pollutant_label": meta["label"],
                "name": meta["name"],
                "unit": meta["unit"],
                "limit_value": limit,
                "sample_count": count,
                "avg_value": avg,
                "max_value": max_value,
                "max_measured_at": max_at,
                "max_station": max_station,
                "min_value": min_value,
                "min_measured_at": min_at,
                "min_station": min_station,
                "exceeded_count": exceeded,
                "exceed_rate": exceed_rate,
                "compliance_rate": round(1 - exceed_rate, 4) if exceed_rate is not None else None,
            }
        )
    return rows


def aggregate_daily_breakdown(filters, start, end):
    """Per-day per-pollutant table, matching the query page group_by=day result set."""
    bucket = func.date(Measurement.measured_at).label("bucket")
    rows = (
        query_service.apply_filters(
            db.session.query(
                bucket,
                Measurement.pollutant.label("pollutant"),
                func.avg(Measurement.value).label("avg_value"),
                func.max(Measurement.value).label("max_value"),
                func.min(Measurement.value).label("min_value"),
                func.count(Measurement.id).label("row_count"),
                func.sum(cast(Measurement.is_exceeded, db.Integer)).label("exceeded_count"),
            ),
            filters,
        )
        .group_by(bucket, Measurement.pollutant)
        .all()
    )
    index = {(str(row.bucket), row.pollutant): row for row in rows}
    days = []
    cursor = start
    while cursor <= end:
        day_key = cursor.isoformat()
        factors = []
        for code in POLLUTANT_CODES:
            row = index.get((day_key, code))
            count = int(row.row_count or 0) if row else 0
            exceeded = int(row.exceeded_count or 0) if row else 0
            factors.append(
                {
                    "pollutant": code,
                    "pollutant_label": POLLUTANTS[code]["label"],
                    "avg_value": _round2(row.avg_value) if row else None,
                    "max_value": _round2(row.max_value) if row else None,
                    "min_value": _round2(row.min_value) if row else None,
                    "sample_count": count,
                    "exceeded_count": exceeded,
                    "exceed_rate": round(exceeded / count, 4) if count else None,
                    "compliance_rate": round(1 - exceeded / count, 4) if count else None,
                }
            )
        day_rows = [r for r in rows if str(r.bucket) == day_key]
        day_count = sum(int(r.row_count or 0) for r in day_rows)
        day_exceeded = sum(int(r.exceeded_count or 0) for r in day_rows)
        days.append(
            {
                "date": day_key,
                "sample_count": day_count,
                "exceeded_count": day_exceeded,
                "exceed_rate": round(day_exceeded / day_count, 4) if day_count else None,
                "factors": factors,
            }
        )
        cursor += timedelta(days=1)
    return days


def pick_primary_pollutant(rows):
    """首要污染物: 有效因子中达标率最低(超标率最高)者, 并报告超标次数.

    无数据、全部达标或无适用限值时返回 None(首要污染物不参与排名)。
    """
    candidates = [
        row
        for row in rows
        if row["sample_count"] > 0
        and row["limit_value"] is not None
        and row["exceeded_count"] > 0
    ]
    if not candidates:
        return None
    candidates.sort(
        key=lambda row: (
            -(row["exceed_rate"] or 0),
            -row["exceeded_count"],
            POLLUTANT_CODES.index(row["pollutant"]),
        )
    )
    top = candidates[0]
    return {
        "pollutant": top["pollutant"],
        "pollutant_label": top["pollutant_label"],
        "exceeded_count": top["exceeded_count"],
        "exceed_rate": top["exceed_rate"],
        "compliance_rate": top["compliance_rate"],
        "avg_value": top["avg_value"],
        "limit_value": top["limit_value"],
        "unit": top["unit"],
    }


# ---------------------------------------------------------------- public API
def _base_filters_from_payload(data):
    """Build the normalised filter dict from the report request payload.

    Reuses the query page parser so filter semantics stay identical.
    """
    args = {
        "station_id": ",".join(str(item) for item in data.get("station_ids", [])),
        "area": ",".join(data.get("areas", [])),
        "pollutant": ",".join(data.get("pollutants", [])),
        "data_source": ",".join(data.get("data_sources", [])),
    }
    filters = query_service.parse_filters(args)
    period = data.get("period")
    if period not in PERIOD_LABELS:
        raise ValidationError(
            "数据周期仅支持: %s" % ", ".join(PERIOD_LABELS.keys()), fields={"period": "unknown"}
        )
    filters["periods"] = [period]
    return filters, period


def _scope_name(filters, period):
    if filters["station_ids"]:
        names = [
            station.name
            for station in Station.query.filter(Station.id.in_(filters["station_ids"])).all()
        ]
        scope = "、".join(names) if names else "选定监测点"
    elif filters["areas"]:
        scope = "、".join(filters["areas"])
    else:
        scope = "全部监测点"
    return "%s · %s" % (scope, PERIOD_LABELS[period])


def generate_report(data):
    report_type = str(data.get("report_type") or "").strip()
    if report_type not in REPORT_TYPE_CHOICES:
        raise ValidationError(
            "报表类型仅支持: %s" % ", ".join(REPORT_TYPE_CHOICES),
            fields={"report_type": "unknown"},
        )
    anchor = parse_date(data.get("date"), "统计日期")
    if anchor is None:
        raise ValidationError("统计日期不能为空", fields={"date": "required"})

    base_filters, period = _base_filters_from_payload(data)
    start, end = resolve_window(report_type, anchor)
    window_filters = _bounded_filters(base_filters, start, end)

    label = period_label(report_type, start, end)
    factor_rows = build_pollutant_rows(window_filters)
    total_summary = query_service.summary(window_filters)
    primary = pick_primary_pollutant(factor_rows)
    daily_breakdown = aggregate_daily_breakdown(window_filters, start, end)

    if total_summary["total"] == 0:
        raise ValidationError(
            "统计周期(%s)内没有符合条件的监测数据, 无法生成报表" % label,
            fields={"date": "no_data"},
        )

    type_label = REPORT_TYPE_LABELS[report_type]
    scope = _scope_name(base_filters, period)
    title = "%s%s(%s)" % (label, type_label, scope)
    total_count = total_summary["total"]
    exceeded_count = total_summary["exceeded_count"]
    overall_exceed_rate = round(exceeded_count / total_count, 4) if total_count else None
    overall_compliance = (
        round(1 - overall_exceed_rate, 4) if overall_exceed_rate is not None else None
    )

    content = {
        "report_type": report_type,
        "report_type_label": type_label,
        "period": period,
        "period_label": PERIOD_LABELS[period],
        "period_start": iso_date(start),
        "period_end": iso_date(end),
        "period_text": label,
        "scope_name": scope,
        "filters": {
            "station_ids": base_filters["station_ids"],
            "areas": base_filters["areas"],
            "pollutants": base_filters["pollutants"],
            "data_sources": base_filters["data_sources"],
            "date_from": iso(window_filters["date_from"]),
            "date_to": iso(window_filters["date_to"]),
        },
        "overall": {
            "sample_count": total_count,
            "exceeded_count": exceeded_count,
            "exceed_rate": overall_exceed_rate,
            "compliance_rate": overall_compliance,
            "avg_value": total_summary["avg_value"],
            "station_count": total_summary["station_count"],
            "first_measured_at": total_summary["first_measured_at"],
            "last_measured_at": total_summary["last_measured_at"],
        },
        "primary_pollutant": primary,
        "factors": factor_rows,
        "daily_breakdown": daily_breakdown,
        "limit_policy": "GB 3095-2012 环境空气质量标准(二级)",
        "generated_at": iso(datetime.now()),
    }

    report = Report(
        title=title,
        report_type=report_type,
        period=period,
        period_start=start,
        period_end=end,
        period_label=label,
        station_ids=",".join(str(item) for item in base_filters["station_ids"]) or None,
        areas=",".join(base_filters["areas"]) or None,
        scope_name=scope,
        creator=(data.get("creator") or "").strip() or None,
        total_count=total_count,
        exceeded_count=exceeded_count,
        compliance_rate=overall_compliance,
        primary_pollutant=primary["pollutant"] if primary else None,
        primary_pollutant_label=primary["pollutant_label"] if primary else None,
        primary_compliance_rate=primary["compliance_rate"] if primary else None,
        content=content,
    )
    db.session.add(report)
    db.session.commit()
    return report


def list_reports(args):
    query = Report.query
    report_type = (args.get("report_type") or "").strip()
    if report_type:
        if report_type not in REPORT_TYPE_CHOICES:
            raise ValidationError(
                "报表类型仅支持: %s" % ", ".join(REPORT_TYPE_CHOICES),
                fields={"report_type": "unknown"},
            )
        query = query.filter(Report.report_type == report_type)
    period = (args.get("period") or "").strip()
    if period:
        if period not in PERIOD_LABELS:
            raise ValidationError("未知数据周期: %s" % period, fields={"period": "unknown"})
        query = query.filter(Report.period == period)
    keyword = (args.get("keyword") or "").strip()
    if keyword:
        like = "%" + keyword + "%"
        query = query.filter(
            or_(Report.title.like(like), Report.scope_name.like(like), Report.creator.like(like))
        )
    date_from = parse_date(args.get("date_from"), "开始日期")
    if date_from:
        query = query.filter(Report.period_start >= date_from)
    date_to = parse_date(args.get("date_to"), "结束日期")
    if date_to:
        query = query.filter(Report.period_end <= date_to)
    return query.order_by(Report.created_at.desc(), Report.id.desc())


def get_report(report_id):
    report = db.session.get(Report, report_id)
    if report is None:
        raise NotFoundError("报表不存在: id=%s" % report_id)
    return report


def delete_report(report):
    db.session.delete(report)
    db.session.commit()

"""报表中心业务逻辑.

关键设计: 报表统计直接复用数据查询模块的 ``parse_filters`` / ``apply_filters``,
与“数据查询”页面走同一条过滤与聚合路径, 因此报表中的均值、极值、超标次数、
达标率都可以在查询页用报表附带的核对条件逐项复算对得上。生成时把结果冻结为
JSON 快照, 后续查看与导出均读取快照, 数据补录不会篡改已出具的报表。
"""
import hashlib
import json
from datetime import date, datetime

from sqlalchemy import cast, func, or_

from ..domain.constants import DATA_SOURCE_LABELS, PERIOD_LABELS
from ..domain.report_periods import REPORT_TYPE_CHOICES, REPORT_TYPE_LABELS, resolve_window, type_prefix
from ..domain.standards import POLLUTANTS, POLLUTANT_CODES, get_pollutant
from ..errors import ConflictError, NotFoundError, ValidationError
from ..extensions import db
from ..models import Measurement, Report, Station
from ..models.base import iso
from ..utils.validation import parse_date
from . import query_service


def _split(value):
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _round2(value):
    return round(float(value), 2) if value is not None else None


# ---------------------------------------------------------------------------
# 作用域 (与数据查询页筛选项一一对应)
# ---------------------------------------------------------------------------
def normalize_scope(raw):
    """Normalise report scope options coming from query params or JSON body."""
    raw = raw or {}

    def _get(key):
        value = raw.get(key)
        if value is None:
            return None
        if isinstance(value, list):
            return ",".join(str(item) for item in value)
        return str(value)

    period = (_get("period") or "daily").strip()
    if period not in PERIOD_LABELS:
        raise ValidationError(
            "统计周期(数据口径)仅支持: %s" % ", ".join(PERIOD_LABELS), fields={"period": "unknown"}
        )

    station_id_raw = _get("station_id")
    station_id = None
    station_name = None
    if station_id_raw:
        try:
            station_id = int(station_id_raw)
        except ValueError:
            raise ValidationError("station_id 必须为整数", fields={"station_id": "invalid_integer"})
        station = db.session.get(Station, station_id)
        if station is None:
            raise ValidationError("监测点不存在: id=%s" % station_id, fields={"station_id": "not_found"})
        station_name = "%s %s" % (station.code, station.name)

    area = (_get("area") or "").strip() or None
    data_source = (_get("data_source") or "").strip() or None
    if data_source and data_source not in DATA_SOURCE_LABELS:
        raise ValidationError("未知数据来源: %s" % data_source, fields={"data_source": "unknown"})

    pollutants = [item.upper() for item in _split(_get("pollutants") or _get("pollutant"))]
    unknown = [item for item in pollutants if item not in POLLUTANT_CODES]
    if unknown:
        raise ValidationError("未知监测因子: %s" % ", ".join(unknown), fields={"pollutant": "unknown"})

    return {
        "period": period,
        "station_id": station_id,
        "station_name": station_name,
        "area": area,
        "pollutants": pollutants,
        "data_source": data_source,
    }


def scope_name(scope):
    parts = []
    if scope["station_name"]:
        parts.append(scope["station_name"])
    elif scope["area"]:
        parts.append(scope["area"])
    else:
        parts.append("全部监测点")
    parts.append(PERIOD_LABELS[scope["period"]])
    if scope["pollutants"]:
        parts.append("、".join(POLLUTANTS[code]["label"] for code in scope["pollutants"]))
    if scope["data_source"]:
        parts.append(DATA_SOURCE_LABELS[scope["data_source"]])
    return " · ".join(parts)


def scope_hash(scope):
    canonical = json.dumps(
        {
            "period": scope["period"],
            "station_id": scope["station_id"],
            "area": scope["area"],
            "pollutants": scope["pollutants"],
            "data_source": scope["data_source"],
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.md5(canonical.encode("utf-8")).hexdigest()


def _query_params(scope, window):
    """The exact query-page request params that reproduce the report numbers."""
    params = {
        "period": scope["period"],
        "date_from": window["start_date"].isoformat(),
        "date_to": window["end_date"].isoformat(),
    }
    if scope["station_id"] is not None:
        params["station_id"] = str(scope["station_id"])
    if scope["area"]:
        params["area"] = scope["area"]
    if scope["pollutants"]:
        params["pollutant"] = ",".join(scope["pollutants"])
    if scope["data_source"]:
        params["data_source"] = scope["data_source"]
    return params


def _parse_window_args(args):
    report_type = (args.get("report_type") or "daily").strip()
    if report_type not in REPORT_TYPE_CHOICES:
        raise ValidationError(
            "报表类型仅支持: %s" % ", ".join(REPORT_TYPE_CHOICES),
            fields={"report_type": "unknown"},
        )
    anchor = parse_date(args.get("date"), "统计日期") or date.today()
    return report_type, resolve_window(report_type, anchor)


# ---------------------------------------------------------------------------
# 报表内容计算 (与查询页共用过滤 / 聚合)
# ---------------------------------------------------------------------------
def _filtered_query(window, scope):
    """Build the Measurement query that is identical to the query page result."""
    args = _query_params(scope, window)
    filters = query_service.parse_filters(args)
    query = query_service.apply_filters(db.session.query(Measurement), filters)
    return query, filters, args


def _extreme_row(base_query, pollutant, descending):
    """Station/time at which a factor reaches its max or min value."""
    direction = Measurement.value.desc() if descending else Measurement.value.asc()
    return (
        base_query.filter(Measurement.pollutant == pollutant)
        .order_by(direction, Measurement.measured_at.desc(), Measurement.id.desc())
        .first()
    )


def _factor_rows(window, scope, active_codes):
    query, _, _ = _filtered_query(window, scope)

    agg_rows = (
        query.with_entities(
            Measurement.pollutant.label("pollutant"),
            func.count(Measurement.id).label("row_count"),
            func.avg(Measurement.value).label("avg_value"),
            func.max(Measurement.value).label("max_value"),
            func.min(Measurement.value).label("min_value"),
            func.sum(cast(Measurement.is_exceeded, db.Integer)).label("exceeded_count"),
            func.sum(
                cast(Measurement.limit_value.isnot(None), db.Integer)
            ).label("applicable_count"),
            func.max(Measurement.limit_value).label("limit_value"),
            func.max(Measurement.exceed_ratio).label("max_ratio"),
        )
        .group_by(Measurement.pollutant)
        .all()
    )
    aggregates = {row.pollutant: row for row in agg_rows}

    # Same base query reused for the max/min/max-ratio extreme rows so that
    # 极值站点与时间也严格限定在报表时间窗与筛选范围内。
    base_query, _, _ = _filtered_query(window, scope)
    factors = []
    for code in active_codes:
        row = aggregates.get(code)
        meta = get_pollutant(code)
        if row is None:
            factors.append(_empty_factor(code, meta, window, scope))
            continue

        count = int(row.row_count or 0)
        applicable = int(row.applicable_count or 0)
        exceeded = int(row.exceeded_count or 0)
        max_row = _extreme_row(base_query, code, descending=True)
        min_row = _extreme_row(base_query, code, descending=False)
        ratio_row = (
            base_query.filter(Measurement.pollutant == code, Measurement.is_exceeded.is_(True))
            .order_by(Measurement.exceed_ratio.desc(), Measurement.measured_at.desc(), Measurement.id.desc())
            .first()
        )

        params = _query_params(scope, window)
        params["pollutant"] = code
        factors.append(
            {
                "pollutant": code,
                "pollutant_label": meta["label"],
                "pollutant_name": meta["name"],
                "unit": meta["unit"],
                "limit_value": float(row.limit_value) if row.limit_value is not None else None,
                "limit_applicable": applicable > 0,
                "avg_value": _round2(row.avg_value),
                "max_value": _round2(row.max_value),
                "max_value_at": iso(max_row.measured_at) if max_row else None,
                "max_station_code": max_row.station.code if max_row and max_row.station else None,
                "max_station_name": max_row.station.name if max_row and max_row.station else None,
                "min_value": _round2(row.min_value),
                "min_value_at": iso(min_row.measured_at) if min_row else None,
                "min_station_code": min_row.station.code if min_row and min_row.station else None,
                "min_station_name": min_row.station.name if min_row and min_row.station else None,
                "count": count,
                "applicable_count": applicable,
                "exceeded_count": exceeded,
                "compliance_rate": round((applicable - exceeded) / applicable, 4) if applicable else None,
                "exceed_rate": round(exceeded / count, 4) if count else 0.0,
                "max_ratio": round(float(row.max_ratio), 3) if row.max_ratio is not None else None,
                "max_ratio_at": iso(ratio_row.measured_at) if ratio_row else None,
                "max_ratio_station_code": ratio_row.station.code if ratio_row and ratio_row.station else None,
                "max_ratio_station_name": ratio_row.station.name if ratio_row and ratio_row.station else None,
                "verification": {
                    "measurements": "/api/query/measurements?" + _qs(params),
                    "statistics": "/api/query/statistics?group_by=pollutant&" + _qs(params),
                    "params": params,
                },
            }
        )
    return factors


def _empty_factor(code, meta, window, scope):
    params = _query_params(scope, window)
    params["pollutant"] = code
    return {
        "pollutant": code,
        "pollutant_label": meta["label"],
        "pollutant_name": meta["name"],
        "unit": meta["unit"],
        "limit_value": meta["limits"].get(scope["period"]),
        "limit_applicable": meta["limits"].get(scope["period"]) is not None,
        "avg_value": None,
        "max_value": None,
        "max_value_at": None,
        "max_station_code": None,
        "max_station_name": None,
        "min_value": None,
        "min_value_at": None,
        "min_station_code": None,
        "min_station_name": None,
        "count": 0,
        "applicable_count": 0,
        "exceeded_count": 0,
        "compliance_rate": None,
        "exceed_rate": 0.0,
        "max_ratio": None,
        "max_ratio_at": None,
        "max_ratio_station_code": None,
        "max_ratio_station_name": None,
        "verification": {
            "measurements": "/api/query/measurements?" + _qs(params),
            "statistics": "/api/query/statistics?group_by=pollutant&" + _qs(params),
            "params": params,
        },
    }


def _qs(params):
    from urllib.parse import urlencode

    return urlencode(params)


def _pick_primary_pollutant(factors):
    """首要污染物: 周期内出现超标的因子中, 最高超标倍数最大者.

    倍数相同时超标次数多者优先, 再次样本量多者优先; 周期内无超标则不评定。
    """
    candidates = [item for item in factors if item["limit_applicable"] and item["exceeded_count"] > 0]
    if not candidates:
        return None
    winner = sorted(
        candidates,
        key=lambda item: (item["max_ratio"] or 0, item["exceeded_count"], item["count"]),
        reverse=True,
    )[0]
    return {
        "pollutant": winner["pollutant"],
        "pollutant_label": winner["pollutant_label"],
        "unit": winner["unit"],
        "limit_value": winner["limit_value"],
        "max_ratio": winner["max_ratio"],
        "max_ratio_at": winner["max_ratio_at"],
        "max_ratio_station_code": winner["max_ratio_station_code"],
        "max_ratio_station_name": winner["max_ratio_station_name"],
        "exceeded_count": winner["exceeded_count"],
        "compliance_rate": winner["compliance_rate"],
        "reason": "周期内最高超标倍数 %.3f 倍, 累计超标 %d 次"
        % (winner["max_ratio"] or 0, winner["exceeded_count"]),
    }


def build_content(report_type, anchor, raw_scope):
    if report_type not in REPORT_TYPE_CHOICES:
        raise ValidationError(
            "报表类型仅支持: %s" % ", ".join(REPORT_TYPE_CHOICES),
            fields={"report_type": "unknown"},
        )
    window = resolve_window(report_type, anchor)
    scope = normalize_scope(raw_scope)
    active_codes = scope["pollutants"] or list(POLLUTANT_CODES)

    query, filters, params = _filtered_query(window, scope)
    overall = query_service.summary(filters)
    factors = _factor_rows(window, scope, active_codes)

    total = sum(item["count"] for item in factors)
    applicable_total = sum(item["applicable_count"] for item in factors)
    exceeded_total = sum(item["exceeded_count"] for item in factors)
    primary = _pick_primary_pollutant(factors)

    content = {
        "title": window["title"],
        "generated_at": iso(datetime.now()),
        "empty": total == 0,
        "report_type": report_type,
        "type_label": REPORT_TYPE_LABELS[report_type],
        "period": {
            "key": window["period_key"],
            "label": window["period_label"],
            "start": iso(window["period_start"]),
            "end": iso(window["period_end"]),
            "anchor": anchor.isoformat(),
        },
        "scope": {
            "name": scope_name(scope),
            "period": scope["period"],
            "period_label": PERIOD_LABELS[scope["period"]],
            "station_id": scope["station_id"],
            "station_name": scope["station_name"],
            "area": scope["area"],
            "pollutants": scope["pollutants"],
            "data_source": scope["data_source"],
            "data_source_label": DATA_SOURCE_LABELS.get(scope["data_source"]) if scope["data_source"] else None,
        },
        "overview": {
            "total": total,
            "applicable_count": applicable_total,
            "exceeded_count": exceeded_total,
            "exceed_rate": round(exceeded_total / total, 4) if total else 0.0,
            "compliance_rate": round(
                (applicable_total - exceeded_total) / applicable_total, 4
            ) if applicable_total else None,
            "station_count": overall["station_count"],
            "factor_count": len([item for item in factors if item["count"] > 0]),
            "first_measured_at": overall["first_measured_at"],
            "last_measured_at": overall["last_measured_at"],
            "avg_value": overall["avg_value"],
            "primary_pollutant": primary["pollutant_label"] if primary else None,
        },
        "factors": factors,
        "primary_pollutant": primary,
        "verification": {
            "measurements_endpoint": "/api/query/measurements?" + _qs(params),
            "statistics_endpoint": "/api/query/statistics?group_by=pollutant&metric=avg&" + _qs(params),
            "params": params,
            "note": "在“数据查询”页面按以上条件(周期/时间范围/监测点或区域等)检索, 总量、超标次数与查询页一致;"
                    "各因子均值/极值/超标次数可用聚合统计 group_by=pollutant 交叉核对;"
                    "达标率 = (有效评价样本数 - 超标次数) / 有效评价样本数, 无小时限值的因子不计入分母。",
        },
    }
    return content, scope, window


# ---------------------------------------------------------------------------
# 生成记录持久化
# ---------------------------------------------------------------------------
def create_report(payload):
    payload = payload or {}
    report_type = (payload.get("report_type") or "daily").strip()
    if report_type not in REPORT_TYPE_CHOICES:
        raise ValidationError(
            "报表类型仅支持: %s" % ", ".join(REPORT_TYPE_CHOICES),
            fields={"report_type": "unknown"},
        )
    anchor = parse_date(payload.get("date"), "统计日期") or date.today()
    scope = normalize_scope(payload)
    content, scope, window = build_content(report_type, anchor, scope)

    if content["overview"]["total"] == 0:
        raise ValidationError(
            "统计周期 %s 内没有符合条件的监测数据, 无法生成报表" % window["period_label"],
            fields={"date": "no_data"},
        )

    overwrite = bool(payload.get("overwrite"))
    generated_by = (str(payload.get("generated_by") or "").strip() or None)
    if generated_by and len(generated_by) > 64:
        raise ValidationError("生成人长度不能超过 64 个字符", fields={"generated_by": "too_long"})

    digest = scope_hash(scope)
    existing = Report.query.filter_by(
        report_type=report_type, period_key=window["period_key"], scope_hash=digest
    ).first()
    if existing and not overwrite:
        raise ConflictError(
            "该周期与统计范围的报表已生成(单号 %s), 如需重新生成请覆盖" % existing.report_no
        )

    if existing:
        existing.period_label = window["period_label"]
        existing.period_start = window["period_start"]
        existing.period_end = window["period_end"]
        existing.scope_name = scope_name(scope)
        existing.scope_filters = _scope_snapshot(scope, window)
        existing.content = content
        existing.generated_by = generated_by
        report = existing
        created = False
    else:
        stamp = window["start_date"].strftime("%Y%m%d")
        if report_type == "weekly":
            stamp = window["start_date"].strftime("%Y%m%d")
        report = Report(
            report_no="%s%s-%s" % (type_prefix(report_type), stamp, digest[:8]),
            report_type=report_type,
            period_key=window["period_key"],
            period_label=window["period_label"],
            period_start=window["period_start"],
            period_end=window["period_end"],
            scope_hash=digest,
            scope_name=scope_name(scope),
            scope_filters=_scope_snapshot(scope, window),
            content=content,
            generated_by=generated_by,
        )
        db.session.add(report)
        created = True

    db.session.commit()
    return report, created


def _scope_snapshot(scope, window):
    return {
        "period": scope["period"],
        "station_id": scope["station_id"],
        "station_name": scope["station_name"],
        "area": scope["area"],
        "pollutants": scope["pollutants"],
        "data_source": scope["data_source"],
        "date_from": window["start_date"].isoformat(),
        "date_to": window["end_date"].isoformat(),
    }


def get_report(report_id):
    report = db.session.get(Report, report_id)
    if report is None:
        raise NotFoundError("报表不存在: id=%s" % report_id)
    return report


def delete_report(report):
    db.session.delete(report)
    db.session.commit()


def report_query(args):
    query = Report.query
    report_type = (args.get("report_type") or "").strip()
    if report_type:
        if report_type not in REPORT_TYPE_CHOICES:
            raise ValidationError(
                "报表类型仅支持: %s" % ", ".join(REPORT_TYPE_CHOICES),
                fields={"report_type": "unknown"},
            )
        query = query.filter(Report.report_type == report_type)
    period_key = (args.get("period_key") or "").strip()
    if period_key:
        query = query.filter(Report.period_key == period_key)
    keyword = (args.get("keyword") or "").strip()
    if keyword:
        like = "%" + keyword + "%"
        query = query.filter(
            or_(Report.report_no.like(like), Report.scope_name.like(like),
                Report.period_label.like(like), Report.period_key.like(like))
        )
    date_from = parse_date(args.get("date_from"), "开始日期") if args.get("date_from") else None
    if date_from:
        query = query.filter(Report.period_start >= datetime.combine(date_from, datetime.min.time()))
    date_to = parse_date(args.get("date_to"), "结束日期") if args.get("date_to") else None
    if date_to:
        query = query.filter(Report.period_end <= datetime.combine(date_to, datetime.max.time()))

    return query.order_by(Report.created_at.desc(), Report.id.desc())


def options_payload():
    return {
        "report_types": [
            {"value": key, "label": label} for key, label in REPORT_TYPE_LABELS.items()
        ],
        "periods": [
            {"value": key, "label": label + ("(报表默认口径)" if key == "daily" else "")}
            for key, label in PERIOD_LABELS.items()
        ],
        "pollutants": [
            {"value": code, "label": meta["label"], "unit": meta["unit"],
             "daily_limit": meta["limits"]["daily"], "hourly_limit": meta["limits"]["hourly"]}
            for code, meta in POLLUTANTS.items()
        ],
    }

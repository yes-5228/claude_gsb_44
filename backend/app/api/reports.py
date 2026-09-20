"""报表中心 API: 生成 / 预览 / 记录列表 / 详情 / 导出 (导出读取冻结快照)."""
import csv
import io
from datetime import date

from flask import Blueprint, Response, request

from ..domain.report_periods import REPORT_TYPE_LABELS
from ..services import report_service
from ..utils.pagination import paginate_query
from ..utils.validation import parse_date
from .helpers import json_payload

bp = Blueprint("reports", __name__)


def _scope_from_args(args):
    return {
        "period": args.get("period"),
        "station_id": args.get("station_id"),
        "area": args.get("area"),
        "pollutants": args.get("pollutant"),
        "data_source": args.get("data_source"),
    }


@bp.get("/", strict_slashes=False)
def list_reports():
    """报表生成记录 (分页, 支持类型/周期/关键字/时间范围过滤)."""
    query = report_service.report_query(request.args)
    return paginate_query(query, lambda row: row.to_dict())


@bp.get("/options")
def report_options():
    return report_service.options_payload()


@bp.get("/preview")
def preview_report():
    """试算: 不落库, 结构与正式报表一致, 便于生成前核对。"""
    report_type = (request.args.get("report_type") or "daily").strip()
    anchor = parse_date(request.args.get("date"), "统计日期") or date.today()
    content, scope, window = report_service.build_content(
        report_type, anchor, _scope_from_args(request.args)
    )
    return {
        "content": content,
        "scope_name": report_service.scope_name(scope),
        "scope_hash": report_service.scope_hash(scope),
        "period_key": window["period_key"],
        "period_label": window["period_label"],
        "already_exists": _existing(report_type, window["period_key"], scope) is not None,
    }


def _existing(report_type, period_key, scope):
    from ..models import Report

    return Report.query.filter_by(
        report_type=report_type,
        period_key=period_key,
        scope_hash=report_service.scope_hash(scope),
    ).first()


@bp.post("/", strict_slashes=False)
def generate_report():
    payload = json_payload()
    report, created = report_service.create_report(payload)
    body = report.to_dict(include_content=True)
    body["created"] = created
    return body, (201 if created else 200)


@bp.get("/<int:report_id>")
def get_report(report_id):
    report = report_service.get_report(report_id)
    return report.to_dict(include_content=True)


@bp.delete("/<int:report_id>")
def remove_report(report_id):
    report = report_service.get_report(report_id)
    report_service.delete_report(report)
    return {"deleted": report_id, "report_no": report.report_no}


@bp.get("/<int:report_id>/export")
def export_report(report_id):
    """导出报表 CSV: 内容直接来自生成时冻结的 JSON 快照。"""
    report = report_service.get_report(report_id)
    content = report.content
    overview = content.get("overview", {})
    period = content.get("period", {})
    scope = content.get("scope", {})

    buffer = io.StringIO()
    writer = csv.writer(buffer)

    writer.writerow([content.get("title", "")])
    writer.writerow(["报表单号", report.report_no])
    writer.writerow(["报表类型", REPORT_TYPE_LABELS.get(report.report_type, report.report_type)])
    writer.writerow(["统计周期", content.get("period", {}).get("label")])
    writer.writerow(["时间范围", "%s ~ %s" % (period.get("start", ""), period.get("end", ""))])
    writer.writerow(["统计范围", scope.get("name")])
    writer.writerow(["数据口径", scope.get("period_label")])
    writer.writerow(["生成时间", report.to_dict().get("generated_at")])
    writer.writerow(["生成人", report.generated_by or ""])
    writer.writerow([])

    writer.writerow([
        "数据总量", "有效评价样本数", "超标次数", "超标率", "达标率",
        "涉及监测点数", "有数据因子数", "首要污染物",
    ])
    writer.writerow([
        overview.get("total"),
        overview.get("applicable_count"),
        overview.get("exceeded_count"),
        _percent(overview.get("exceed_rate")),
        _percent(overview.get("compliance_rate")),
        overview.get("station_count"),
        overview.get("factor_count"),
        overview.get("primary_pollutant") or ("无(周期内无超标)" if overview.get("total") else ""),
    ])
    writer.writerow([])

    writer.writerow([
        "监测因子", "单位", "限值", "均值", "最大值", "最大值时间", "最大值站点",
        "最小值", "最小值时间", "最小值站点", "样本数", "有效评价样本数",
        "超标次数", "超标率", "达标率", "最高超标倍数", "最高倍数时间", "最高倍数站点",
    ])
    for item in content.get("factors", []):
        writer.writerow([
            item["pollutant_label"],
            item["unit"],
            _num(item["limit_value"]),
            _num(item["avg_value"]),
            _num(item["max_value"]),
            item.get("max_value_at") or "",
            _station(item.get("max_station_code"), item.get("max_station_name")),
            _num(item["min_value"]),
            item.get("min_value_at") or "",
            _station(item.get("min_station_code"), item.get("min_station_name")),
            item["count"],
            item["applicable_count"],
            item["exceeded_count"],
            _percent(item["exceed_rate"]),
            _percent(item["compliance_rate"]),
            _num(item["max_ratio"]),
            item.get("max_ratio_at") or "",
            _station(item.get("max_ratio_station_code"), item.get("max_ratio_station_name")),
        ])
    writer.writerow([])

    primary = content.get("primary_pollutant")
    writer.writerow([
        "首要污染物",
        (primary["pollutant_label"] + "(" + primary["reason"] + ")") if primary else "无, 周期内未出现超标",
    ])
    verification = content.get("verification", {})
    writer.writerow(["核对接口", verification.get("measurements_endpoint", "")])
    writer.writerow(["聚合核对", verification.get("statistics_endpoint", "")])
    writer.writerow(["口径说明", verification.get("note", "")])

    filename = "air_quality_report_%s.csv" % report.report_no
    payload = "\ufeff" + buffer.getvalue()
    return Response(
        payload,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=%s" % filename},
    )


def _num(value):
    return "" if value is None else value


def _percent(rate):
    if rate is None:
        return ""
    return "%.1f%%" % (round(float(rate), 4) * 100)


def _station(code, name):
    if not code and not name:
        return ""
    return ("%s %s" % (code or "", name or "")).strip()

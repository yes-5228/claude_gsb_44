"""报表中心 API: 生成 / 列表 / 详情 / 导出 / 删除."""
import csv
import io
from datetime import datetime

from flask import Blueprint, Response, request

from ..domain.constants import PERIOD_LABELS
from ..models import REPORT_TYPE_LABELS
from ..services import report_service
from ..utils.pagination import paginate_query
from .helpers import json_payload

bp = Blueprint("reports", __name__)


@bp.get("/", strict_slashes=False)
def list_reports():
    """报表生成记录(分页), 支持类型/周期/关键字/统计日期筛选."""
    query = report_service.list_reports(request.args)
    return paginate_query(query, lambda row: row.to_dict())


@bp.post("/", strict_slashes=False)
def create_report():
    """生成日报 / 周报 / 月报, 同时保留生成记录与完整快照."""
    report = report_service.generate_report(json_payload())
    return report.to_dict(include_content=True), 201


@bp.get("/options")
def report_options():
    return {
        "report_types": [
            {"value": key, "label": label} for key, label in REPORT_TYPE_LABELS.items()
        ],
        "periods": [{"value": key, "label": label} for key, label in PERIOD_LABELS.items()],
    }


@bp.get("/<int:report_id>")
def get_report(report_id):
    return report_service.get_report(report_id).to_dict(include_content=True)


@bp.delete("/<int:report_id>")
def remove_report(report_id):
    report = report_service.get_report(report_id)
    report_service.delete_report(report)
    return {"deleted": report_id}


@bp.get("/<int:report_id>/export")
def export_report(report_id):
    """导出报表 CSV: 概要 + 各因子统计 + (周/月报)逐日明细, 数字与报表快照一致."""
    report = report_service.get_report(report_id)
    content = report.content
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    def blank():
        writer.writerow([])

    writer.writerow(["空气质量监测%s" % content["report_type_label"]])
    writer.writerow(["报表名称", report.title])
    writer.writerow(["统计周期", content["period_text"]])
    writer.writerow(["统计范围", content["scope_name"]])
    writer.writerow(["数据周期", content["period_label"]])
    writer.writerow(["执行标准", content["limit_policy"]])
    writer.writerow(["生成时间", content["generated_at"].replace("T", " ")])
    blank()

    overall = content["overall"]
    writer.writerow(["一、总体情况"])
    writer.writerow([
        "有效数据量", "超标次数", "超标率", "达标率", "平均浓度", "涉及监测点数",
    ])
    writer.writerow([
        overall["sample_count"],
        overall["exceeded_count"],
        _percent(overall["exceed_rate"]),
        _percent(overall["compliance_rate"]),
        overall["avg_value"],
        overall["station_count"],
    ])
    blank()

    primary = content.get("primary_pollutant")
    writer.writerow(["二、首要污染物"])
    if primary:
        writer.writerow([
            "首要污染物", "单位", "均值", "限值", "超标次数", "超标率", "达标率",
        ])
        writer.writerow([
            primary["pollutant_label"],
            primary["unit"],
            primary["avg_value"],
            primary["limit_value"],
            primary["exceeded_count"],
            _percent(primary["exceed_rate"]),
            _percent(primary["compliance_rate"]),
        ])
    else:
        writer.writerow(["统计周期内各评价因子均达标, 无首要污染物"])
    blank()

    writer.writerow(["三、各监测因子统计"])
    writer.writerow([
        "监测因子", "单位", "样本数", "均值", "最大值", "最大值出现时间", "最大值出现站点",
        "最小值", "最小值出现时间", "最小值出现站点", "限值", "超标次数", "超标率", "达标率",
    ])
    for row in content["factors"]:
        writer.writerow([
            row["pollutant_label"],
            row["unit"],
            row["sample_count"],
            row["avg_value"] if row["avg_value"] is not None else "",
            row["max_value"] if row["max_value"] is not None else "",
            (row["max_measured_at"] or "").replace("T", " "),
            row["max_station"] or "",
            row["min_value"] if row["min_value"] is not None else "",
            (row["min_measured_at"] or "").replace("T", " "),
            row["min_station"] or "",
            row["limit_value"] if row["limit_value"] is not None else "未设限值",
            row["exceeded_count"],
            _percent(row["exceed_rate"]),
            _percent(row["compliance_rate"]),
        ])

    breakdown = content.get("daily_breakdown") or []
    has_daily = any(day["sample_count"] for day in breakdown)
    if content["report_type"] in ("weekly", "monthly") and has_daily:
        blank()
        writer.writerow(["四、逐日因子均值"])
        header = ["日期", "数据量", "超标次数"]
        header.extend(factor["pollutant_label"] for factor in breakdown[0]["factors"])
        writer.writerow(header)
        for day in breakdown:
            if not day["sample_count"]:
                continue
            line = [day["date"], day["sample_count"], day["exceeded_count"]]
            line.extend(
                factor["avg_value"] if factor["avg_value"] is not None else ""
                for factor in day["factors"]
            )
            writer.writerow(line)

    filename = "monitoring_report_%s_%s.csv" % (
        content["report_type"],
        datetime.now().strftime("%Y%m%d%H%M%S"),
    )
    payload = "\ufeff" + buffer.getvalue()
    return Response(
        payload,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=%s" % filename},
    )


def _percent(rate):
    """Render a 0~1 rate as a percentage string, matching the UI rounding."""
    if rate is None:
        return ""
    return "%.1f%%" % (round(float(rate) * 100, 4))

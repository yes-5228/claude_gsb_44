"""报表周期定义: 日报 / 周报 / 月报的时间窗口与标签."""
from datetime import date, datetime, time, timedelta

REPORT_TYPE_LABELS = {"daily": "日报", "weekly": "周报", "monthly": "月报"}

REPORT_TYPE_CHOICES = tuple(REPORT_TYPE_LABELS.keys())

_TYPE_PREFIX = {"daily": "D", "weekly": "W", "monthly": "M"}


def resolve_window(report_type, anchor):
    """Return the inclusive [start, end] time window for a report.

    ``anchor`` is any date inside the target period:
    - daily:  the anchor day itself
    - weekly: ISO 周, 周一 00:00 ~ 周日 23:59:59.999999
    - monthly: 自然月, 1 日 ~ 月末
    """
    if report_type == "daily":
        start_day = end_day = anchor
        period_key = anchor.strftime("%Y-%m-%d")
        period_label = anchor.strftime("%Y-%m-%d")
    elif report_type == "weekly":
        iso_year, iso_week, iso_weekday = anchor.isocalendar()
        start_day = anchor - timedelta(days=iso_weekday - 1)
        end_day = start_day + timedelta(days=6)
        period_key = "%04d-W%02d" % (iso_year, iso_week)
        period_label = "%s (%s ~ %s)" % (
            period_key,
            start_day.strftime("%m-%d"),
            end_day.strftime("%m-%d"),
        )
    elif report_type == "monthly":
        start_day = anchor.replace(day=1)
        if start_day.month == 12:
            next_month = date(start_day.year + 1, 1, 1)
        else:
            next_month = date(start_day.year, start_day.month + 1, 1)
        end_day = next_month - timedelta(days=1)
        period_key = anchor.strftime("%Y-%m")
        period_label = period_key
    else:
        raise ValueError("未知报表类型: %s" % report_type)

    return {
        "report_type": report_type,
        "type_label": REPORT_TYPE_LABELS[report_type],
        "anchor": anchor,
        "start_date": start_day,
        "end_date": end_day,
        "period_start": datetime.combine(start_day, time.min),
        "period_end": datetime.combine(end_day, time.max),
        "period_key": period_key,
        "period_label": period_label,
        "title": "%s 空气质量监测%s" % (period_label, REPORT_TYPE_LABELS[report_type]),
    }


def type_prefix(report_type):
    return _TYPE_PREFIX.get(report_type, "R")

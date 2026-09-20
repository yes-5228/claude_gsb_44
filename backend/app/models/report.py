"""监测报表生成记录 (日报 / 周报 / 月报)."""
from ..extensions import db
from .base import TimestampMixin, iso, iso_date

REPORT_TYPE_LABELS = {"daily": "日报", "weekly": "周报", "monthly": "月报"}


class Report(TimestampMixin, db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    report_type = db.Column(db.String(16), nullable=False, index=True)
    period = db.Column(db.String(16), nullable=False)
    period_start = db.Column(db.Date, nullable=False, index=True)
    period_end = db.Column(db.Date, nullable=False)
    period_label = db.Column(db.String(32), nullable=False)

    # 生成报表时实际使用的过滤条件(归一化后), 保证可复现/可比对
    station_ids = db.Column(db.String(255))
    areas = db.Column(db.String(255))
    scope_name = db.Column(db.String(255))
    creator = db.Column(db.String(64))

    total_count = db.Column(db.Integer, nullable=False, default=0)
    exceeded_count = db.Column(db.Integer, nullable=False, default=0)
    compliance_rate = db.Column(db.Float)
    primary_pollutant = db.Column(db.String(16))
    primary_pollutant_label = db.Column(db.String(32))
    primary_compliance_rate = db.Column(db.Float)

    # 完整报表快照(JSON), 报表内容一经生成不随后续数据变动而改变
    content = db.Column(db.JSON, nullable=False)

    def to_dict(self, include_content=False):
        payload = {
            "id": self.id,
            "title": self.title,
            "report_type": self.report_type,
            "report_type_label": REPORT_TYPE_LABELS.get(self.report_type, self.report_type),
            "period": self.period,
            "period_start": iso_date(self.period_start),
            "period_end": iso_date(self.period_end),
            "period_label": self.period_label,
            "station_ids": self.station_ids,
            "areas": self.areas,
            "scope_name": self.scope_name,
            "creator": self.creator,
            "total_count": self.total_count,
            "exceeded_count": self.exceeded_count,
            "compliance_rate": self.compliance_rate,
            "primary_pollutant": self.primary_pollutant,
            "primary_pollutant_label": self.primary_pollutant_label,
            "primary_compliance_rate": self.primary_compliance_rate,
            "created_at": iso(self.created_at),
        }
        if include_content:
            payload["content"] = self.content
        return payload

    def __repr__(self):
        return "<Report %s %s>" % (self.report_type, self.period_label)

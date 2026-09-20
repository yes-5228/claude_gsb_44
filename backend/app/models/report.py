"""报表生成记录 (报表内容以 JSON 快照形式冻结, 复现/导出均与生成时一致)."""
from ..domain.report_periods import REPORT_TYPE_LABELS
from ..extensions import db
from .base import TimestampMixin, iso, iso_date


class Report(TimestampMixin, db.Model):
    __tablename__ = "reports"
    __table_args__ = (
        db.UniqueConstraint(
            "report_type", "period_key", "scope_hash",
            name="uq_report_type_period_scope",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    report_no = db.Column(db.String(40), unique=True, nullable=False, index=True)
    report_type = db.Column(db.String(16), nullable=False, index=True)
    period_key = db.Column(db.String(20), nullable=False, index=True)
    period_label = db.Column(db.String(40), nullable=False)
    period_start = db.Column(db.DateTime, nullable=False)
    period_end = db.Column(db.DateTime, nullable=False)
    scope_hash = db.Column(db.String(32), nullable=False, default="default")
    scope_name = db.Column(db.String(120))
    scope_filters = db.Column(db.JSON)
    content = db.Column(db.JSON, nullable=False)
    generated_by = db.Column(db.String(64))

    def scope_text(self):
        return self.scope_name or "全部监测点"

    def to_dict(self, include_content=False):
        overview = self.content.get("overview", {}) if self.content else {}
        payload = {
            "id": self.id,
            "report_no": self.report_no,
            "report_type": self.report_type,
            "report_type_label": REPORT_TYPE_LABELS.get(self.report_type, self.report_type),
            "period_key": self.period_key,
            "period_label": self.period_label,
            "period_start": iso(self.period_start),
            "period_end": iso(self.period_end),
            "scope_name": self.scope_text(),
            "scope_filters": self.scope_filters or {},
            "generated_by": self.generated_by,
            "generated_at": iso(self.created_at),
            "title": self.content.get("title") if self.content else None,
            "overview": overview,
        }
        if include_content:
            payload["content"] = self.content
        return payload

    def __repr__(self):
        return "<Report %s %s>" % (self.report_no, self.period_key)

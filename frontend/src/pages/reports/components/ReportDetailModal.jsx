import Modal from '../../../components/common/Modal.jsx'
import Tag from '../../../components/common/Tag.jsx'
import { Loading } from '../../../components/common/Feedback.jsx'
import { REPORT_TYPE_LABELS, REPORT_TYPE_TONE } from '../../../constants/index.js'
import { formatDateTime, formatNumber, formatPercent } from '../../../utils/format.js'

function StatLine({ label, value, tone }) {
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className="stat-value" style={{ color: tone ? `var(--${tone})` : undefined }}>{value}</div>
    </div>
  )
}

export default function ReportDetailModal({ report, loading, onClose, onVerify, onExport, exporting }) {
  if (!report) return null
  const content = report.content || {}
  const overall = content.overall || {}
  const primary = content.primary_pollutant
  const factors = content.factors || []
  const breakdown = (content.daily_breakdown || []).filter((day) => day.sample_count > 0)

  return (
    <Modal
      open
      width="wide"
      drawer
      title={report.title}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose} disabled={loading}>
            关闭
          </button>
          <button type="button" className="btn" onClick={() => onVerify(report)} disabled={loading}>
            🔍 到查询页核对
          </button>
          <button type="button" className="btn btn-primary" onClick={() => onExport(report)} disabled={loading || exporting}>
            {exporting ? '导出中...' : '导出 CSV'}
          </button>
        </>
      }
    >
      <div className="stack">
        {loading || !content.period_start ? (
          <Loading text="正在加载报表..." />
        ) : (
          <>
        <div className="inline">
          <Tag tone={REPORT_TYPE_TONE[report.report_type]}>
            {REPORT_TYPE_LABELS[report.report_type] || report.report_type}
          </Tag>
          <span className="muted small">{content.scope_name}</span>
          <span className="muted small">统计区间 {content.period_start} ~ {content.period_end}</span>
          <span className="spacer" />
          <span className="muted small">生成于 {formatDateTime(report.created_at)}</span>
        </div>

        <div className="stat-grid">
          <StatLine label="有效数据量" value={overall.sample_count} />
          <StatLine label="超标次数" value={overall.exceeded_count} tone={overall.exceeded_count ? 'danger' : undefined} />
          <StatLine
            label="达标率"
            value={formatPercent(overall.compliance_rate)}
            tone={(overall.compliance_rate ?? 1) < 0.9 ? 'danger' : 'success'}
          />
          <StatLine label="平均浓度" value={formatNumber(overall.avg_value)} />
          <StatLine label="涉及监测点" value={overall.station_count} />
        </div>

        <div className="card" style={{ boxShadow: 'none' }}>
          <div className="card-header">
            <h3>首要污染物</h3>
            <span className="hint">按各因子达标率最低(超标率最高)确定, 无限值因子不参与</span>
          </div>
          <div className="card-body tight">
            {primary ? (
              <div className="inline">
                <Tag tone="warning" title={`超标 ${primary.exceeded_count} 次`}>
                  {primary.pollutant_label}
                </Tag>
                <span className="small">
                  均值 <strong>{formatNumber(primary.avg_value)}</strong> {primary.unit} / 限值{' '}
                  {formatNumber(primary.limit_value)} {primary.unit}
                </span>
                <span className="small">
                  超标 <strong className="danger-text">{primary.exceeded_count}</strong> 次 · 超标率{' '}
                  {formatPercent(primary.exceed_rate)} · 达标率{' '}
                  <strong className="danger-text">{formatPercent(primary.compliance_rate)}</strong>
                </span>
              </div>
            ) : (
              <div className="small muted">统计周期内各评价因子均达标, 无首要污染物。</div>
            )}
          </div>
        </div>

        <div className="card" style={{ boxShadow: 'none' }}>
          <div className="card-header">
            <h3>各监测因子统计</h3>
            <span className="hint">均值 / 极值 / 超标次数 / 达标率, 与数据查询页聚合统计同口径</span>
          </div>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>监测因子</th>
                  <th className="text-right">样本数</th>
                  <th className="text-right">均值</th>
                  <th className="text-right">最大值(时间/站点)</th>
                  <th className="text-right">最小值(时间/站点)</th>
                  <th className="text-right">限值</th>
                  <th className="text-right">超标次数</th>
                  <th className="text-right">达标率</th>
                </tr>
              </thead>
              <tbody>
                {factors.map((row) => (
                  <tr key={row.pollutant}>
                    <td>
                      <strong>{row.pollutant_label}</strong>
                      <span className="muted small"> {row.unit}</span>
                    </td>
                    <td className="text-right">{row.sample_count || '-'}</td>
                    <td className="text-right strong">{formatNumber(row.avg_value)}</td>
                    <td className="text-right">
                      {row.sample_count ? (
                        <>
                          <span className={row.max_value > (row.limit_value ?? Infinity) ? 'danger-text strong' : ''}>
                            {formatNumber(row.max_value)}
                          </span>
                          <div className="muted small">
                            {(row.max_measured_at || '').replace('T', ' ').slice(0, 16)}
                            {row.max_station ? ` · ${row.max_station}` : ''}
                          </div>
                        </>
                      ) : (
                        '-'
                      )}
                    </td>
                    <td className="text-right">
                      {row.sample_count ? (
                        <>
                          {formatNumber(row.min_value)}
                          <div className="muted small">
                            {(row.min_measured_at || '').replace('T', ' ').slice(0, 16)}
                            {row.min_station ? ` · ${row.min_station}` : ''}
                          </div>
                        </>
                      ) : (
                        '-'
                      )}
                    </td>
                    <td className="text-right">{row.limit_value === null ? '未设限值' : formatNumber(row.limit_value)}</td>
                    <td className="text-right">
                      {row.exceeded_count ? <span className="danger-text strong">{row.exceeded_count}</span> : 0}
                    </td>
                    <td className="text-right">
                      {row.sample_count ? (
                        <span className={row.compliance_rate < 0.9 ? 'danger-text' : 'success-text'}>
                          {formatPercent(row.compliance_rate)}
                        </span>
                      ) : (
                        '-'
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {breakdown.length > 0 ? (
          <div className="card" style={{ boxShadow: 'none' }}>
            <div className="card-header">
              <h3>逐日因子均值</h3>
              <span className="hint">
                {REPORT_TYPE_LABELS[report.report_type]}区间内 {breakdown.length} 个有数据的自然日
              </span>
            </div>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>日期</th>
                    <th className="text-right">数据量</th>
                    <th className="text-right">超标次数</th>
                    {(breakdown[0]?.factors || []).map((factor) => (
                      <th key={factor.pollutant} className="text-right">
                        {factor.pollutant_label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {breakdown.map((day) => (
                    <tr key={day.date}>
                      <td className="cell-nowrap">{day.date}</td>
                      <td className="text-right">{day.sample_count}</td>
                      <td className="text-right">
                        {day.exceeded_count ? <span className="danger-text strong">{day.exceeded_count}</span> : 0}
                      </td>
                      {day.factors.map((factor) => (
                        <td key={factor.pollutant} className="text-right">
                          {factor.sample_count ? formatNumber(factor.avg_value) : <span className="muted">-</span>}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        <div className="small muted">
          执行标准: {content.limit_policy} · 数字口径与「数据查询」页一致, 可点击下方「到查询页核对」按相同条件交叉验证。
        </div>
          </>
        )}
      </div>
    </Modal>
  )
}

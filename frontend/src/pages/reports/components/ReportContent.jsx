import { useNavigate } from 'react-router-dom'
import StatCard from '../../../components/common/StatCard.jsx'
import Tag from '../../../components/common/Tag.jsx'
import { formatComplianceRate, formatDateTime, formatNumber, formatPercent } from '../../../utils/format.js'

/** 报表正文: 预览与详情共用, 所有数字来自同一份 content 快照。 */
export default function ReportContent({ content, frozen = false }) {
  const navigate = useNavigate()
  const overview = content?.overview ?? {}
  const factors = content?.factors ?? []
  const primary = content?.primary_pollutant
  const scope = content?.scope ?? {}
  const period = content?.period ?? {}
  const verification = content?.verification ?? {}

  const goVerify = (pollutant) => {
    const params = new URLSearchParams(verification.params ?? {})
    if (pollutant) params.set('pollutant', pollutant)
    params.set('group_by', 'pollutant')
    params.set('metric', 'avg')
    params.set('from', 'report')
    navigate(`/query?${params.toString()}`)
  }

  return (
    <div className="stack">
      <div className="report-meta">
        <div className="report-meta-row">
          <span className="muted">统计周期</span>
          <strong>{period.label}</strong>
          <span className="muted">数据口径</span>
          <strong>{scope.period_label}</strong>
          <span className="muted">时间范围</span>
          <strong>
            {formatDateTime(period.start)} ~ {formatDateTime(period.end)}
          </strong>
        </div>
        <div className="report-meta-row">
          <span className="muted">统计范围</span>
          <strong>{scope.name}</strong>
          {frozen ? <Tag tone="info">已冻结 · 生成于 {formatDateTime(content.generated_at)}</Tag> : null}
        </div>
      </div>

      {content.empty ? (
        <div className="alert alert-warning">该周期与范围内没有监测数据。</div>
      ) : null}

      <div className="stat-grid">
        <StatCard label="数据总量" value={overview.total} foot={`涉及 ${overview.station_count} 个监测点 · ${overview.factor_count} 个因子`} />
        <StatCard
          label="超标次数"
          value={overview.exceeded_count}
          tone={overview.exceeded_count ? 'danger' : undefined}
          foot={`超标率 ${formatPercent(overview.exceed_rate)}`}
        />
        <StatCard
          label="综合达标率"
          value={formatComplianceRate(overview.compliance_rate)}
          tone={overview.compliance_rate !== null && overview.compliance_rate < 0.9 ? 'warning' : undefined}
          foot={`有效评价样本 ${overview.applicable_count} 条`}
        />
        <StatCard
          label="首要污染物"
          value={primary ? primary.pollutant_label : '无'}
          tone={primary ? 'danger' : undefined}
          foot={primary ? primary.reason : '周期内未出现超标'}
        />
      </div>

      {primary ? (
        <div className="alert alert-danger">
          <strong>首要污染物: {primary.pollutant_label}</strong>
          <span style={{ marginLeft: 10 }}>{primary.reason}</span>
          {primary.max_ratio_station_name ? (
            <span style={{ marginLeft: 10 }} className="muted">
              · 出现于 {primary.max_ratio_station_code} {primary.max_ratio_station_name} · {formatDateTime(primary.max_ratio_at)}
            </span>
          ) : null}
        </div>
      ) : (
        <div className="alert alert-success">周期内各评价因子均无超标, 不评定首要污染物。</div>
      )}

      <div className="table-wrap">
        <table className="data-table report-table">
          <thead>
            <tr>
              <th>监测因子</th>
              <th className="text-right">均值</th>
              <th className="text-right">最大值</th>
              <th>最大值出现</th>
              <th className="text-right">最小值</th>
              <th>最小值出现</th>
              <th className="text-right">样本数</th>
              <th className="text-right">有效评价</th>
              <th className="text-right">超标次数</th>
              <th className="text-right">超标率</th>
              <th className="text-right">达标率</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {factors.map((factor) => {
              const exceeded = factor.exceeded_count > 0
              return (
                <tr key={factor.pollutant} className={exceeded ? 'row-danger' : ''}>
                  <td>
                    <div className="strong">{factor.pollutant_label}</div>
                    <div className="hint">
                      {factor.unit}
                      {factor.limit_value !== null && factor.limit_value !== undefined
                        ? ` · 限值 ${formatNumber(factor.limit_value)}`
                        : ' · 该口径无限值'}
                      {factor.max_ratio ? ` · 最高 ${formatNumber(factor.max_ratio, 3)} 倍` : ''}
                    </div>
                  </td>
                  <td className="text-right strong">{formatNumber(factor.avg_value)}</td>
                  <td className={`text-right strong ${exceeded ? 'danger-text' : ''}`}>{formatNumber(factor.max_value)}</td>
                  <td className="small">
                    {factor.max_value_at
                      ? `${formatDateTime(factor.max_value_at)} · ${factor.max_station_code || ''} ${factor.max_station_name || ''}`
                      : '-'}
                  </td>
                  <td className="text-right">{formatNumber(factor.min_value)}</td>
                  <td className="small">
                    {factor.min_value_at
                      ? `${formatDateTime(factor.min_value_at)} · ${factor.min_station_code || ''} ${factor.min_station_name || ''}`
                      : '-'}
                  </td>
                  <td className="text-right">{factor.count}</td>
                  <td className="text-right">{factor.applicable_count}</td>
                  <td className={`text-right strong ${exceeded ? 'danger-text' : ''}`}>{factor.exceeded_count}</td>
                  <td className="text-right">{formatPercent(factor.exceed_rate)}</td>
                  <td className="text-right">
                    {factor.compliance_rate === null ? (
                      <span className="muted">不参评</span>
                    ) : (
                      <span className={factor.compliance_rate < 0.9 ? 'danger-text' : 'success-text'}>
                        {formatComplianceRate(factor.compliance_rate)}
                      </span>
                    )}
                  </td>
                  <td>
                    <button type="button" className="btn btn-sm btn-ghost" onClick={() => goVerify(factor.pollutant)}>
                      在查询页核对
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="report-verify">
        <div className="hint">
          达标率 = (有效评价样本数 − 超标次数) ÷ 有效评价样本数; 该口径未设限值的因子(如 PM2.5/PM10 小时值)不参与达标率计算。
          均值、极值与查询页聚合统计 (group_by=pollutant) 口径一致, 超标次数、样本数与查询页检索结果一致。
        </div>
        <button type="button" className="btn btn-sm" onClick={() => goVerify()}>
          按报表条件打开数据查询页
        </button>
      </div>
    </div>
  )
}

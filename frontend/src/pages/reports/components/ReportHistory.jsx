import { SectionCard } from '../../../components/common/Card.jsx'
import { Alert } from '../../../components/common/Feedback.jsx'
import Pagination from '../../../components/common/Pagination.jsx'
import Tag from '../../../components/common/Tag.jsx'
import { formatDateTime } from '../../../utils/format.js'

const TYPE_TONE = { daily: 'primary', weekly: 'info', monthly: 'success' }

export default function ReportHistory({
  records,
  total,
  page,
  pages,
  pageSize,
  loading,
  error,
  filters,
  onFiltersChange,
  onPageChange,
  onPageSizeChange,
  onReload,
  onView,
  onExport,
  onDelete
}) {
  return (
    <SectionCard
      title="报表生成记录"
      hint="已生成的报表数字随快照永久留痕, 导出与查看均读取该快照"
      actions={
        <button type="button" className="btn btn-sm" onClick={onReload} disabled={loading}>
          刷新
        </button>
      }
    >
      <div className="stack">
        <div className="history-filters inline">
          <select
            className="select"
            style={{ width: 130 }}
            value={filters.report_type || ''}
            onChange={(event) => onFiltersChange({ ...filters, report_type: event.target.value })}
          >
            <option value="">全部类型</option>
            <option value="daily">日报</option>
            <option value="weekly">周报</option>
            <option value="monthly">月报</option>
          </select>
          <input
            className="input"
            style={{ width: 180 }}
            placeholder="单号 / 周期 / 范围关键字"
            value={filters.keyword || ''}
            onChange={(event) => onFiltersChange({ ...filters, keyword: event.target.value })}
            onKeyDown={(event) => event.key === 'Enter' && onReload()}
          />
          <input
            type="date"
            className="input"
            style={{ width: 150 }}
            value={filters.date_from || ''}
            onChange={(event) => onFiltersChange({ ...filters, date_from: event.target.value })}
          />
          <span className="muted">至</span>
          <input
            type="date"
            className="input"
            style={{ width: 150 }}
            value={filters.date_to || ''}
            onChange={(event) => onFiltersChange({ ...filters, date_to: event.target.value })}
          />
          <button type="button" className="btn btn-sm btn-primary" onClick={onReload}>
            查询
          </button>
        </div>

        {error ? <Alert tone="error">{error.message}</Alert> : null}

        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>报表单号</th>
                <th>类型</th>
                <th>统计周期</th>
                <th>统计范围</th>
                <th className="text-right">数据量</th>
                <th className="text-right">超标次数</th>
                <th>达标率</th>
                <th>首要污染物</th>
                <th>生成人</th>
                <th>生成时间</th>
                <th style={{ width: 180 }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {records.map((row) => {
                const overview = row.overview || {}
                return (
                  <tr key={row.id}>
                    <td className="mono small">{row.report_no}</td>
                    <td>
                      <Tag tone={TYPE_TONE[row.report_type]}>{row.report_type_label}</Tag>
                    </td>
                    <td>{row.period_label}</td>
                    <td className="small">{row.scope_name}</td>
                    <td className="text-right">{overview.total ?? '-'}</td>
                    <td className={`text-right ${overview.exceeded_count ? 'danger-text strong' : ''}`}>
                      {overview.exceeded_count ?? '-'}
                    </td>
                    <td>
                      {overview.compliance_rate === null || overview.compliance_rate === undefined
                        ? '-'
                        : `${(Number(overview.compliance_rate) * 100).toFixed(1)}%`}
                    </td>
                    <td>
                      {overview.primary_pollutant ? (
                        <Tag tone="danger">{overview.primary_pollutant}</Tag>
                      ) : (
                        <span className="muted">无</span>
                      )}
                    </td>
                    <td>{row.generated_by || '-'}</td>
                    <td className="small">{formatDateTime(row.generated_at)}</td>
                    <td>
                      <div className="btn-group">
                        <button type="button" className="btn btn-sm" onClick={() => onView(row)}>
                          查看
                        </button>
                        <button type="button" className="btn btn-sm btn-primary" onClick={() => onExport(row)}>
                          导出
                        </button>
                        <button type="button" className="btn btn-sm btn-danger" onClick={() => onDelete(row)}>
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
              {!loading && records.length === 0 ? (
                <tr>
                  <td colSpan={11} className="muted" style={{ textAlign: 'center', padding: 28 }}>
                    暂无报表记录, 请先在上方生成报表
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        <Pagination
          page={page}
          pages={pages}
          total={total}
          pageSize={pageSize}
          onPageChange={onPageChange}
          onPageSizeChange={onPageSizeChange}
        />
      </div>
    </SectionCard>
  )
}

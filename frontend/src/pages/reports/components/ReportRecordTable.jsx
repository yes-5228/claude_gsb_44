import DataTable from '../../../components/common/DataTable.jsx'
import Tag from '../../../components/common/Tag.jsx'
import { REPORT_TYPE_LABELS, REPORT_TYPE_TONE } from '../../../constants/index.js'
import { formatDateTime, formatPercent } from '../../../utils/format.js'

export default function ReportRecordTable({ rows, loading, onView, onExport, onDelete, exportingId }) {
  const columns = [
    {
      key: 'period_label',
      title: '统计周期',
      className: 'cell-nowrap',
      render: (row) => (
        <div>
          <div className="strong">{row.period_label}</div>
          <div className="muted small">
            {row.period_start} ~ {row.period_end}
          </div>
        </div>
      )
    },
    {
      key: 'report_type',
      title: '类型',
      render: (row) => <Tag tone={REPORT_TYPE_TONE[row.report_type]}>{REPORT_TYPE_LABELS[row.report_type] || row.report_type}</Tag>
    },
    { key: 'scope_name', title: '统计范围' },
    { key: 'total_count', title: '数据量', align: 'right' },
    {
      key: 'exceeded_count',
      title: '超标次数',
      align: 'right',
      render: (row) => <span className={row.exceeded_count ? 'danger-text strong' : ''}>{row.exceeded_count}</span>
    },
    {
      key: 'compliance_rate',
      title: '达标率',
      align: 'right',
      render: (row) => (
        <span className={(row.compliance_rate ?? 1) < 0.9 ? 'danger-text' : 'success-text'}>
          {formatPercent(row.compliance_rate)}
        </span>
      )
    },
    {
      key: 'primary_pollutant_label',
      title: '首要污染物',
      render: (row) =>
        row.primary_pollutant_label ? <Tag tone="warning">{row.primary_pollutant_label}</Tag> : <span className="muted">无</span>
    },
    { key: 'creator', title: '制表人', render: (row) => row.creator || '-' },
    { key: 'created_at', title: '生成时间', className: 'cell-nowrap', render: (row) => formatDateTime(row.created_at) },
    {
      key: 'actions',
      title: '操作',
      className: 'cell-nowrap',
      render: (row) => (
        <div className="btn-group">
          <button type="button" className="btn btn-sm" onClick={() => onView(row)}>
            查看
          </button>
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => onExport(row)}
            disabled={exportingId === row.id}
          >
            {exportingId === row.id ? '导出中' : '导出'}
          </button>
          <button type="button" className="btn btn-sm btn-danger" onClick={() => onDelete(row)}>
            删除
          </button>
        </div>
      )
    }
  ]

  return (
    <DataTable
      columns={columns}
      rows={rows}
      loading={loading}
      emptyText="还没有生成记录, 请先在上方生成报表"
      emptyIcon="📑"
      onRowClick={onView}
    />
  )
}

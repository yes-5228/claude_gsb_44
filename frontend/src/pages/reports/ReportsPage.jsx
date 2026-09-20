import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  exportReportUrl,
  generateReport,
  getReport,
  listReports,
  removeReport
} from '../../api/reports.js'
import { downloadFile } from '../../api/client.js'
import Pagination from '../../components/common/Pagination.jsx'
import { SectionCard } from '../../components/common/Card.jsx'
import { Alert } from '../../components/common/Feedback.jsx'
import ConfirmDialog from '../../components/common/ConfirmDialog.jsx'
import { useToast } from '../../components/common/ToastProvider.jsx'
import { useListQuery } from '../../hooks/useListQuery.js'
import { saveBlob } from '../../utils/download.js'
import ReportDetailModal from './components/ReportDetailModal.jsx'
import ReportGenerateCard from './components/ReportGenerateCard.jsx'
import ReportRecordFilters from './components/ReportRecordFilters.jsx'
import ReportRecordTable from './components/ReportRecordTable.jsx'

const INITIAL_FILTERS = { report_type: '', period: '', keyword: '', date_from: '', date_to: '' }

export default function ReportsPage() {
  const toast = useToast()
  const navigate = useNavigate()
  const query = useListQuery(listReports, INITIAL_FILTERS, { pageSize: 10 })
  const [generating, setGenerating] = useState(false)
  const [detail, setDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [exportingId, setExportingId] = useState(null)
  const [pendingDelete, setPendingDelete] = useState(null)
  const [deleting, setDeleting] = useState(false)

  const openDetail = async (row) => {
    setDetail({ ...row, content: null })
    setDetailLoading(true)
    try {
      const full = await getReport(row.id)
      setDetail(full)
    } catch (error) {
      toast.error(error.message)
      setDetail(null)
    } finally {
      setDetailLoading(false)
    }
  }

  const handleGenerate = async (payload) => {
    setGenerating(true)
    try {
      const report = await generateReport(payload)
      toast.success(`${report.period_label}${report.report_type_label}已生成`)
      query.reload()
      setDetail(report)
    } catch (error) {
      toast.error(error.message)
    } finally {
      setGenerating(false)
    }
  }

  const handleExport = async (row) => {
    setExportingId(row.id)
    try {
      const blob = await downloadFile(exportReportUrl(row.id))
      saveBlob(blob, `${row.period_label}${row.report_type_label}.csv`)
      toast.success('报表已导出')
    } catch (error) {
      toast.error(error.message)
    } finally {
      setExportingId(null)
    }
  }

  const handleVerify = (report) => {
    const filters = report.content?.filters || {}
    const params = new URLSearchParams()
    if (report.period) params.set('period', report.period)
    if (filters.date_from) params.set('date_from', filters.date_from.slice(0, 10))
    if (filters.date_to) params.set('date_to', filters.date_to.slice(0, 10))
    if ((filters.station_ids || []).length === 1) params.set('station_id', filters.station_ids[0])
    if ((filters.areas || []).length === 1) params.set('area', filters.areas[0])
    if ((filters.data_sources || []).length === 1) params.set('data_source', filters.data_sources[0])
    params.set('group_by', 'pollutant')
    navigate(`/query?${params.toString()}`)
  }

  const confirmDelete = async () => {
    setDeleting(true)
    try {
      await removeReport(pendingDelete.id)
      toast.success('报表记录已删除')
      if (detail?.id === pendingDelete.id) setDetail(null)
      setPendingDelete(null)
      query.reload()
    } catch (error) {
      toast.error(error.message)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <>
      <ReportGenerateCard loading={generating} onGenerate={handleGenerate} />

      <ReportRecordFilters
        value={query.filters}
        loading={query.loading}
        onSubmit={(next) => query.setFilters(next)}
        onReset={(next) => query.setFilters(next)}
      />

      {query.error ? <Alert tone="error">{query.error.message}</Alert> : null}

      <SectionCard
        title="生成记录"
        hint="报表生成时留存完整快照, 可随时查看、导出; 后续数据变化不影响历史报表"
        actions={
          <button type="button" className="btn btn-sm" onClick={query.reload} disabled={query.loading}>
            刷新
          </button>
        }
      >
        <ReportRecordTable
          rows={query.items}
          loading={query.loading}
          onView={openDetail}
          onExport={handleExport}
          onDelete={setPendingDelete}
          exportingId={exportingId}
        />
        <Pagination
          page={query.page}
          pages={query.pages}
          total={query.total}
          pageSize={query.pageSize}
          onPageChange={query.setPage}
          onPageSizeChange={query.setPageSize}
        />
      </SectionCard>

      {detail ? (
        <ReportDetailModal
          report={detail}
          loading={detailLoading}
          onClose={() => setDetail(null)}
          onVerify={handleVerify}
          onExport={handleExport}
          exporting={exportingId === detail.id}
        />
      ) : null}

      <ConfirmDialog
        open={!!pendingDelete}
        title="删除报表记录"
        message={`确认删除「${pendingDelete?.title}」吗?`}
        detail="删除后报表生成记录与快照将无法恢复, 监测原始数据不受影响。"
        confirmText="删除"
        danger
        busy={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </>
  )
}

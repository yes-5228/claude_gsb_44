import { useCallback, useState } from 'react'
import {
  deleteReport,
  exportReportUrl,
  generateReport,
  getReport,
  listReports,
  previewReport
} from '../../api/reports.js'
import { downloadFile } from '../../api/client.js'
import { Alert } from '../../components/common/Feedback.jsx'
import ConfirmDialog from '../../components/common/ConfirmDialog.jsx'
import { useToast } from '../../components/common/ToastProvider.jsx'
import { useListQuery } from '../../hooks/useListQuery.js'
import { saveBlob } from '../../utils/download.js'
import ReportBuilder from './components/ReportBuilder.jsx'
import ReportDetailModal from './components/ReportDetailModal.jsx'
import ReportHistory from './components/ReportHistory.jsx'
import ReportPreviewPanel from './components/ReportPreviewPanel.jsx'

const todayStr = () => new Date().toISOString().slice(0, 10)

const INITIAL_BUILDER = {
  report_type: 'daily',
  date: todayStr(),
  period: 'daily',
  station_id: '',
  area: '',
  pollutants: [],
  data_source: '',
  overwrite: false,
  generated_by: ''
}

const INITIAL_HISTORY_FILTERS = { report_type: '', keyword: '', date_from: '', date_to: '' }

export default function ReportsPage() {
  const toast = useToast()
  const history = useListQuery(listReports, INITIAL_HISTORY_FILTERS, { pageSize: 10 })

  const [builder, setBuilder] = useState(INITIAL_BUILDER)
  const [preview, setPreview] = useState({ data: null, loading: false, error: null })
  const [generating, setGenerating] = useState(false)
  const [detail, setDetail] = useState({ open: false, loading: false, error: null, report: null })
  const [pendingDelete, setPendingDelete] = useState(null)
  const [deleting, setDeleting] = useState(false)

  const toParams = useCallback(
    (form) => ({
      report_type: form.report_type,
      date: form.date,
      period: form.period,
      station_id: form.station_id,
      area: form.area,
      pollutant: form.pollutants,
      data_source: form.data_source
    }),
    []
  )

  const runPreview = useCallback(
    async (form) => {
      if (!form.date) {
        toast.warning('请先选择统计日期')
        return
      }
      setPreview({ data: null, loading: true, error: null })
      try {
        const data = await previewReport(toParams(form))
        setPreview({ data, loading: false, error: null })
      } catch (error) {
        setPreview({ data: null, loading: false, error })
      }
    },
    [toParams, toast]
  )

  const runGenerate = useCallback(
    async (form) => {
      if (!form.date) {
        toast.warning('请先选择统计日期')
        return
      }
      setGenerating(true)
      try {
        const payload = {
          report_type: form.report_type,
          date: form.date,
          period: form.period,
          station_id: form.station_id ? Number(form.station_id) : undefined,
          area: form.area || undefined,
          pollutants: form.pollutants.length ? form.pollutants : undefined,
          data_source: form.data_source || undefined,
          overwrite: Boolean(form.overwrite),
          generated_by: form.generated_by?.trim() || undefined
        }
        const report = await generateReport(payload)
        toast.success(
          report.created
            ? `报表 ${report.report_no} 已生成`
            : `报表 ${report.report_no} 已按最新数据覆盖更新`
        )
        setPreview({ data: null, loading: false, error: null })
        setDetail({ open: true, loading: false, error: null, report })
        history.reload()
      } catch (error) {
        if (error.status === 409) {
          toast.warning(error.message)
        } else {
          toast.error(error.message)
        }
      } finally {
        setGenerating(false)
      }
    },
    [history, toast]
  )

  const openDetail = useCallback(async (row) => {
    setDetail({ open: true, loading: true, error: null, report: null })
    try {
      const report = await getReport(row.id)
      setDetail({ open: true, loading: false, error: null, report })
    } catch (error) {
      setDetail({ open: true, loading: false, error, report: null })
    }
  }, [])

  const handleExport = useCallback(
    async (row) => {
      try {
        const blob = await downloadFile(exportReportUrl(row.id))
        saveBlob(blob, `${row.report_no}_${row.period_label}.csv`)
        toast.success(`报表 ${row.report_no} 已导出`)
      } catch (error) {
        toast.error(error.message)
      }
    },
    [toast]
  )

  const handleDelete = useCallback(async () => {
    if (!pendingDelete) return
    setDeleting(true)
    try {
      await deleteReport(pendingDelete.id)
      toast.success(`报表 ${pendingDelete.report_no} 已删除`)
      setPendingDelete(null)
      history.reload()
    } catch (error) {
      toast.error(error.message)
    } finally {
      setDeleting(false)
    }
  }, [pendingDelete, history, toast])

  return (
    <>
      <ReportBuilder
        value={builder}
        onChange={setBuilder}
        onPreview={runPreview}
        onGenerate={runGenerate}
        previewing={preview.loading}
        generating={generating}
      />

      {generating ? <Alert tone="info">正在汇总并冻结报表数字...</Alert> : null}

      <ReportPreviewPanel
        data={preview.data}
        loading={preview.loading}
        error={preview.error}
        onGenerate={() => runGenerate(builder)}
        generating={generating}
      />

      <ReportHistory
        records={history.items}
        total={history.total}
        page={history.page}
        pages={history.pages}
        pageSize={history.pageSize}
        loading={history.loading}
        error={history.error}
        filters={history.filters}
        onFiltersChange={history.setFilters}
        onPageChange={history.setPage}
        onPageSizeChange={history.setPageSize}
        onReload={history.reload}
        onView={openDetail}
        onExport={handleExport}
        onDelete={(row) => setPendingDelete(row)}
      />

      <ReportDetailModal
        open={detail.open}
        loading={detail.loading}
        error={detail.error}
        report={detail.report}
        onClose={() => setDetail((prev) => ({ ...prev, open: false }))}
        onExport={handleExport}
      />

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        danger
        busy={deleting}
        title="删除报表"
        message={`确认删除报表「${pendingDelete?.report_no || ''}」吗?`}
        detail="仅删除报表生成记录与冻结快照, 不会影响原始监测数据。"
        confirmText="确认删除"
        onConfirm={handleDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </>
  )
}

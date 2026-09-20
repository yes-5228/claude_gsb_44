import Modal from '../../../components/common/Modal.jsx'
import { Alert, Loading } from '../../../components/common/Feedback.jsx'
import ReportContent from './ReportContent.jsx'

export default function ReportDetailModal({ open, loading, error, report, onClose, onExport }) {
  const footer = (
    <>
      <button type="button" className="btn" onClick={onClose}>
        关闭
      </button>
      <button
        type="button"
        className="btn btn-primary"
        onClick={() => report && onExport(report)}
        disabled={!report}
      >
        导出 CSV
      </button>
    </>
  )

  return (
    <Modal open={open} title={report?.title || '报表详情'} onClose={onClose} footer={footer} width="wide">
      {loading ? <Loading text="正在加载报表..." /> : null}
      {error ? <Alert tone="error">{error.message}</Alert> : null}
      {!loading && report?.content ? <ReportContent content={report.content} frozen /> : null}
    </Modal>
  )
}

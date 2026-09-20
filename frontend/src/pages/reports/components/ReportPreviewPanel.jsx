import { SectionCard } from '../../../components/common/Card.jsx'
import { Alert, EmptyState, Loading } from '../../../components/common/Feedback.jsx'
import Tag from '../../../components/common/Tag.jsx'
import ReportContent from './ReportContent.jsx'

export default function ReportPreviewPanel({ data, loading, error, onGenerate, generating }) {
  return (
    <SectionCard
      title="报表试算预览"
      hint="试算不落库、不占用报表单号; 确认数字无误后再生成报表"
      actions={
        data ? (
          <>
            {data.already_exists ? (
              <Tag tone="warning" title="同一周期与统计范围已生成报表">
                已有同条件报表
              </Tag>
            ) : (
              <Tag tone="success">可生成新报表</Tag>
            )}
            <button type="button" className="btn btn-primary btn-sm" onClick={onGenerate} disabled={generating}>
              {generating ? '生成中...' : '采用当前条件生成'}
            </button>
          </>
        ) : null
      }
    >
      {error ? <Alert tone="error">{error.message}</Alert> : null}
      {loading ? <Loading text="正在试算..." /> : null}
      {!loading && !data && !error ? (
        <EmptyState text="选择报表类型、日期与统计范围后点击“试算预览”" icon="🧮" />
      ) : null}
      {!loading && data?.content ? <ReportContent content={data.content} /> : null}
    </SectionCard>
  )
}

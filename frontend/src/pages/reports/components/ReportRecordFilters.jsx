import { useEffect, useState } from 'react'
import { FilterPanel } from '../../../components/common/Card.jsx'
import { Input, Select } from '../../../components/common/FormField.jsx'

const TYPE_OPTIONS = [
  { value: 'daily', label: '日报' },
  { value: 'weekly', label: '周报' },
  { value: 'monthly', label: '月报' }
]

const PERIOD_OPTIONS = [
  { value: 'daily', label: '日均值' },
  { value: 'hourly', label: '小时均值' }
]

const EMPTY = { report_type: '', period: '', keyword: '', date_from: '', date_to: '' }

export default function ReportRecordFilters({ value, loading, onSubmit, onReset }) {
  const [draft, setDraft] = useState(value)

  useEffect(() => {
    setDraft(value)
  }, [value])

  const update = (key) => (event) => setDraft({ ...draft, [key]: event.target.value })

  return (
    <FilterPanel
      loading={loading}
      onSearch={() => onSubmit(draft)}
      onReset={() => {
        setDraft(EMPTY)
        onReset(EMPTY)
      }}
    >
      <label className="field">
        <span className="field-label">报表类型</span>
        <Select value={draft.report_type || ''} onChange={update('report_type')} placeholder="全部类型" options={TYPE_OPTIONS} />
      </label>
      <label className="field">
        <span className="field-label">数据周期</span>
        <Select value={draft.period || ''} onChange={update('period')} placeholder="全部周期" options={PERIOD_OPTIONS} />
      </label>
      <label className="field">
        <span className="field-label">关键字</span>
        <Input
          placeholder="报表名称 / 范围 / 制表人"
          value={draft.keyword || ''}
          onChange={update('keyword')}
          onKeyDown={(event) => event.key === 'Enter' && onSubmit(draft)}
        />
      </label>
      <label className="field">
        <span className="field-label">周期开始 ≥</span>
        <Input type="date" value={draft.date_from || ''} onChange={update('date_from')} />
      </label>
      <label className="field">
        <span className="field-label">周期结束 ≤</span>
        <Input type="date" value={draft.date_to || ''} onChange={update('date_to')} />
      </label>
    </FilterPanel>
  )
}

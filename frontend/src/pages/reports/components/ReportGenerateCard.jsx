import { useMemo, useState } from 'react'
import { SectionCard } from '../../../components/common/Card.jsx'
import { Field, Input, Select } from '../../../components/common/FormField.jsx'
import { usePollutantMeta, useStationOptions } from '../../../hooks/useOptions.js'

const TYPE_OPTIONS = [
  { value: 'daily', label: '日报(按自然日)' },
  { value: 'weekly', label: '周报(周一至周日)' },
  { value: 'monthly', label: '月报(自然月)' }
]

const PERIOD_OPTIONS = [
  { value: 'daily', label: '日均值(24 小时平均)' },
  { value: 'hourly', label: '小时均值' }
]

const SOURCE_OPTIONS = [
  { value: 'manual', label: '手工录入' },
  { value: 'device', label: '设备上传' },
  { value: 'import', label: '历史导入' }
]

function toLocalDateInput(date = new Date()) {
  const pad = (value) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

function windowHint(type, dateValue) {
  if (!dateValue) return '选择统计周期内任意一天, 自动定位所属日 / 周 / 月'
  const day = new Date(`${dateValue}T00:00:00`)
  if (Number.isNaN(day.getTime())) return ''
  const fmt = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  if (type === 'daily') return `统计区间: ${fmt(day)}`
  if (type === 'weekly') {
    const monday = new Date(day)
    monday.setDate(day.getDate() - ((day.getDay() + 6) % 7))
    const sunday = new Date(monday)
    sunday.setDate(monday.getDate() + 6)
    return `统计区间: ${fmt(monday)} ~ ${fmt(sunday)}`
  }
  const first = new Date(day.getFullYear(), day.getMonth(), 1)
  const last = new Date(day.getFullYear(), day.getMonth() + 1, 0)
  return `统计区间: ${fmt(first)} ~ ${fmt(last)}`
}

export default function ReportGenerateCard({ loading, onGenerate }) {
  const { data: stationData } = useStationOptions()
  const { data: pollutantData } = usePollutantMeta()
  const [form, setForm] = useState({
    report_type: 'daily',
    date: toLocalDateInput(),
    period: 'daily',
    station_id: '',
    area: '',
    data_source: '',
    creator: ''
  })

  const update = (key) => (event) => setForm({ ...form, [key]: event.target.value })
  const hint = useMemo(() => windowHint(form.report_type, form.date), [form.report_type, form.date])

  const submit = () => {
    const payload = {
      report_type: form.report_type,
      period: form.period,
      date: form.date,
      station_ids: form.station_id ? [Number(form.station_id)] : [],
      areas: form.area ? [form.area] : [],
      data_sources: form.data_source ? [form.data_source] : [],
      pollutants: (pollutantData?.items ?? []).map((item) => item.code),
      creator: form.creator || null
    }
    onGenerate(payload)
  }

  return (
    <SectionCard title="生成监测报表" hint="报表口径与数据查询页完全一致, 生成后留存快照, 不随后续数据变化">
      <div className="filter-bar">
        <Field label="报表类型">
          <Select value={form.report_type} onChange={update('report_type')} options={TYPE_OPTIONS} />
        </Field>
        <Field label="统计日期" hint={hint}>
          <Input type="date" value={form.date} onChange={update('date')} />
        </Field>
        <Field label="数据周期">
          <Select value={form.period} onChange={update('period')} options={PERIOD_OPTIONS} />
        </Field>
        <Field label="监测点">
          <Select
            value={form.station_id}
            onChange={update('station_id')}
            placeholder="全部监测点"
            options={(stationData?.items ?? []).map((item) => ({
              value: String(item.id),
              label: `${item.code} ${item.name}`
            }))}
          />
        </Field>
        <Field label="所属区域">
          <Select
            value={form.area}
            onChange={update('area')}
            placeholder="全部区域"
            options={(stationData?.areas ?? []).map((area) => ({ value: area, label: area }))}
          />
        </Field>
        <Field label="数据来源">
          <Select value={form.data_source} onChange={update('data_source')} placeholder="全部来源" options={SOURCE_OPTIONS} />
        </Field>
        <Field label="制表人">
          <Input placeholder="选填" value={form.creator} onChange={update('creator')} maxLength={64} />
        </Field>
        <div className="filter-actions">
          <button type="button" className="btn btn-primary" onClick={submit} disabled={loading}>
            {loading ? '生成中...' : '生成报表'}
          </button>
        </div>
      </div>
    </SectionCard>
  )
}

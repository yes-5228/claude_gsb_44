import { useEffect, useState } from 'react'
import { FilterPanel } from '../../../components/common/Card.jsx'
import { Field, Input, Select } from '../../../components/common/FormField.jsx'
import { usePollutantMeta, useStationOptions } from '../../../hooks/useOptions.js'

const TYPE_OPTIONS = [
  { value: 'daily', label: '日报 (选定日期当天)' },
  { value: 'weekly', label: '周报 (日期所在 ISO 周, 周一至周日)' },
  { value: 'monthly', label: '月报 (日期所在自然月)' }
]

const PERIOD_OPTIONS = [
  { value: 'daily', label: '日均值 (24 小时平均, 默认口径)' },
  { value: 'hourly', label: '小时均值' }
]

const SOURCE_OPTIONS = [
  { value: 'manual', label: '手工录入' },
  { value: 'device', label: '设备上传' },
  { value: 'import', label: '历史导入' }
]

const todayStr = () => new Date().toISOString().slice(0, 10)

const EMPTY_FORM = {
  report_type: 'daily',
  date: '',
  period: 'daily',
  station_id: '',
  area: '',
  pollutants: [],
  data_source: '',
  overwrite: false,
  generated_by: ''
}

export default function ReportBuilder({ value, onChange, onPreview, onGenerate, previewing, generating }) {
  const [draft, setDraft] = useState(value)
  const { data: stationData } = useStationOptions()
  const { data: pollutantData } = usePollutantMeta()

  useEffect(() => {
    setDraft(value)
  }, [value])

  const update = (key) => (event) => {
    const next = { ...draft, [key]: event.target.value }
    setDraft(next)
    onChange(next)
  }

  const togglePollutant = (code) => {
    const exists = draft.pollutants.includes(code)
    const next = {
      ...draft,
      pollutants: exists ? draft.pollutants.filter((item) => item !== code) : [...draft.pollutants, code]
    }
    setDraft(next)
    onChange(next)
  }

  const reset = () => {
    const next = { ...EMPTY_FORM, date: todayStr() }
    setDraft(next)
    onChange(next)
  }

  useEffect(() => {
    if (!draft.date) {
      const next = { ...draft, date: todayStr() }
      setDraft(next)
      onChange(next)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <FilterPanel
      loading={previewing || generating}
      extra={
        <div className="inline" style={{ justifyContent: 'space-between' }}>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={Boolean(value.overwrite)}
              onChange={(event) => onChange({ ...value, overwrite: event.target.checked })}
            />
            <span>已存在同周期同范围报表时覆盖重新生成</span>
          </label>
          <div className="hint">报表按下方数据口径统计, 生成后数字冻结留痕</div>
        </div>
      }
      onSearch={() => onPreview(draft)}
      onReset={reset}
    >
      <Field label="报表类型" required>
        <Select value={draft.report_type} onChange={update('report_type')} options={TYPE_OPTIONS} />
      </Field>
      <Field label="统计日期" required hint="取该日期所在的日 / 周 / 月">
        <Input type="date" value={draft.date || ''} onChange={update('date')} />
      </Field>
      <Field label="数据口径" required>
        <Select value={draft.period} onChange={update('period')} options={PERIOD_OPTIONS} />
      </Field>
      <Field label="监测点">
        <Select
          value={draft.station_id || ''}
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
          value={draft.area || ''}
          onChange={update('area')}
          placeholder="全部区域"
          options={(stationData?.areas ?? []).map((area) => ({ value: area, label: area }))}
        />
      </Field>
      <Field label="数据来源">
        <Select
          value={draft.data_source || ''}
          onChange={update('data_source')}
          placeholder="全部来源"
          options={SOURCE_OPTIONS}
        />
      </Field>
      <Field label="生成人">
        <Input
          placeholder="可选, 用于生成留痕"
          maxLength={64}
          value={draft.generated_by || ''}
          onChange={update('generated_by')}
        />
      </Field>
      <Field label="监测因子" hint="不勾选则统计全部因子" className="span-wide">
        <div className="checkbox-group">
          {(pollutantData?.items ?? []).map((item) => (
            <label key={item.code} className="checkbox">
              <input
                type="checkbox"
                checked={draft.pollutants.includes(item.code)}
                onChange={() => togglePollutant(item.code)}
              />
              <span>{item.label}</span>
            </label>
          ))}
        </div>
      </Field>
      <div className="filter-actions" style={{ alignSelf: 'end' }}>
        <button type="button" className="btn" onClick={() => onPreview(draft)} disabled={previewing}>
          {previewing ? '试算中...' : '试算预览'}
        </button>
        <button type="button" className="btn btn-primary" onClick={() => onGenerate(draft)} disabled={generating}>
          {generating ? '生成中...' : '生成报表'}
        </button>
      </div>
    </FilterPanel>
  )
}

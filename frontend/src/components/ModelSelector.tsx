import { useEffect, useState } from 'react'
import { Select, Tag, Typography } from 'antd'
import { api } from '../api/client'
import type { ModelInfo, SelectedModel } from '../types'

interface Props {
  value: SelectedModel | null
  onChange: (model: SelectedModel) => void
  dark?: boolean
}

const PROVIDER_META: Record<string, string> = {
  deepseek: 'DeepSeek',
  mimo: '小米 MiMo',
}

export default function ModelSelector({ value, onChange, dark = false }: Props) {
  const [models, setModels] = useState<ModelInfo[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.listModels()
      .then((list) => {
        setModels(list)
        if (!value) {
          const first = list.find((item) => item.available) || list[0]
          if (first) onChange({ provider: first.provider, model: first.model })
        }
      })
      .catch(() => undefined)
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const options = models.map((item) => ({
    value: `${item.provider}::${item.model}`,
    disabled: !item.available,
    label: (
      <span style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
        <span>{PROVIDER_META[item.provider] ?? item.provider} · {item.model}</span>
        {!item.available && <Typography.Text type="warning" style={{ fontSize: 12 }}>未配置</Typography.Text>}
      </span>
    ),
  }))

  return (
    <div style={{ display: 'flex', flexDirection: dark ? 'column' : 'row', alignItems: dark ? 'stretch' : 'center', gap: 8, width: '100%', minWidth: 0 }}>
      <Select
        size="middle"
        loading={loading}
        value={value ? `${value.provider}::${value.model}` : undefined}
        placeholder="选择模型"
        options={options}
        onChange={(key) => {
          const [provider, model] = key.split('::')
          onChange({ provider, model })
        }}
        style={{
          width: '100%', minWidth: 0,
          color: dark ? '#fff' : undefined,
        }}
        popupMatchSelectWidth={false}
      />
      {!models.some((item) => item.available) && !loading && <Tag color="warning" style={{ alignSelf: 'flex-start', marginInlineEnd: 0 }}>未配置密钥</Tag>}
    </div>
  )
}

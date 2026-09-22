/**
 * 模型选择器组件（Ant Design Select）。
 *
 * 展示后端可用的 LLM 模型列表（DeepSeek / 小米 MiMo），允许用户在运行时切换模型。
 * 未配置 API Key 的提供商以禁用项呈现并在右侧标注，直观展示"多模型支持 + 运行时切换"能力。
 */
import { useEffect, useState } from 'react'
import { Badge, Select, Tag } from 'antd'
import { api } from '../api/client'
import type { ModelInfo, SelectedModel } from '../types'

interface Props {
  /** 当前选中的模型 */
  value: SelectedModel | null
  /** 选中变化回调 */
  onChange: (model: SelectedModel) => void
}

/** provider 标识 → 友好展示名 */
const PROVIDER_META: Record<string, { label: string }> = {
  deepseek: { label: 'DeepSeek' },
  mimo: { label: '小米 MiMo' },
}

/** 渲染 provider 的友好名称 */
function providerLabel(provider: string): string {
  return PROVIDER_META[provider]?.label ?? provider
}

export default function ModelSelector({ value, onChange }: Props) {
  const [models, setModels] = useState<ModelInfo[]>([])
  const [loading, setLoading] = useState(true)

  // 组件挂载时拉取可用模型列表
  useEffect(() => {
    api
      .listModels()
      .then((list) => {
        setModels(list)
        // 若尚未选择模型，默认选中第一个可用模型
        if (!value) {
          const first = list.find((m) => m.available) || list[0]
          if (first) onChange({ provider: first.provider, model: first.model })
        }
      })
      .catch(() => {
        /* 忽略：网络异常时下拉框为空，不阻塞主流程 */
      })
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const selected = value
    ? models.find((m) => m.provider === value.provider && m.model === value.model)
    : undefined
  const anyAvailable = models.some((m) => m.available)

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <Badge
        status={selected?.available ? 'success' : 'error'}
        title={selected?.available ? '该模型已就绪' : '该模型未配置密钥'}
      />
      <Select
        size="small"
        loading={loading}
        style={{ flex: 1, minWidth: 0 }}
        value={value ? `${value.provider}::${value.model}` : undefined}
        placeholder="选择模型"
        options={models.map((m) => ({
          value: `${m.provider}::${m.model}`,
          label: `${providerLabel(m.provider)} · ${m.model}${m.available ? '' : '（未配置密钥）'}`,
          disabled: !m.available,
        }))}
        onChange={(v) => {
          const [provider, model] = (v as string).split('::')
          onChange({ provider, model })
        }}
      />
      {!anyAvailable && !loading && (
        <Tag color="warning" title="请在后端 .env 中填写 DEEPSEEK_API_KEY 或 MIMO_API_KEY">
          未配置密钥
        </Tag>
      )}
    </div>
  )
}

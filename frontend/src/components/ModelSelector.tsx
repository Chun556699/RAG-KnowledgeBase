/**
 * 模型选择器组件。
 *
 * 展示后端可用的 LLM 模型列表（DeepSeek / 小米 MiMo），允许用户在运行时切换模型。
 * 未配置 API Key 的提供商会以禁用样式呈现，并提示前往配置，
 * 直观展示"多模型支持 + 运行时切换"能力。
 */
import { useEffect, useState } from 'react'
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

  /** 下拉选择时解析出 provider 与 model 并回调 */
  const handleSelect = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const [provider, model] = e.target.value.split('::')
    onChange({ provider, model })
  }

  if (loading) return <span className="tag">加载模型…</span>

  const selected = value
    ? models.find((m) => m.provider === value.provider && m.model === value.model)
    : undefined
  const anyAvailable = models.some((m) => m.available)

  return (
    <div className="model-selector">
      <span
        className={`status-dot ${selected?.available ? 'ok' : 'err'}`}
        title={selected?.available ? '该模型已就绪' : '该模型未配置密钥'}
      />
      <select
        className="model-select"
        value={value ? `${value.provider}::${value.model}` : ''}
        onChange={handleSelect}
        title="选择用于对话与 Agent 的大语言模型"
      >
        {models.map((m) => (
          <option
            key={`${m.provider}::${m.model}`}
            value={`${m.provider}::${m.model}`}
            disabled={!m.available}
          >
            {providerLabel(m.provider)} · {m.model}
            {m.available ? '' : '（未配置密钥）'}
          </option>
        ))}
      </select>
      {!anyAvailable && (
        <span className="tag warn" title="请在后端 .env 中填写 DEEPSEEK_API_KEY 或 MIMO_API_KEY">
          未配置密钥
        </span>
      )}
    </div>
  )
}

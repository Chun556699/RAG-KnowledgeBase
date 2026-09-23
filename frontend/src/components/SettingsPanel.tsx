/**
 * 系统设置面板。
 *
 * 在网页端完成大模型（LLM）的接入与切换，并管理嵌入与重排序服务：
 *  - LLM 提供商：填写/更新 API Key、端点、模型，切换默认模型，测试连通性；
 *  - 重排序：开关两阶段重排序，配置密钥/端点/模型/候选数/精排数并测试连通性；
 *  - 嵌入：查看/更新嵌入提供商、端点、模型、维度（切换后可能需重建索引）。
 *
 * 脱密保护：所有密钥仅以掩码（如 sk-a****wxyz）展示，真实密钥永不出网页；
 * 输入框留空或回填掩码占位视为「不修改」，避免误清空后端已保存的真实密钥。
 */
import { useEffect, useState } from 'react'
import {
  App,
  Badge,
  Button,
  Card,
  Col,
  Input,
  InputNumber,
  Row,
  Space,
  Spin,
  Switch,
  Tag,
} from 'antd'
import {
  ApiOutlined,
  CheckOutlined,
  CloudServerOutlined,
  DatabaseOutlined,
  KeyOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { api, ApiError } from '../api/client'
import type { SettingsSnapshot } from '../types'

/** LLM 提供商草稿：仅承载用户本次编辑的增量 */
interface LLMDraft {
  api_key: string
  base_url: string
  model: string
}

/** 重排序草稿 */
interface RerankerDraft {
  enabled: boolean
  api_key: string
  base_url: string
  model: string
  top_n: number
  candidate_k: number
}

/** 嵌入草稿 */
interface EmbeddingDraft {
  provider: string
  api_key: string
  base_url: string
  model: string
  dimension: number
}

/** 字段标签 */
const FieldLabel = ({ children }: { children: React.ReactNode }) => (
  <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', margin: '10px 0 4px' }}>
    {children}
  </div>
)

export default function SettingsPanel() {
  const { message } = App.useApp()
  const [snapshot, setSnapshot] = useState<SettingsSnapshot | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')

  // 各分区的编辑草稿，null 表示未进入编辑
  const [llmDrafts, setLlmDrafts] = useState<Record<string, LLMDraft>>({})
  const [reranker, setReranker] = useState<RerankerDraft | null>(null)
  const [embedding, setEmbedding] = useState<EmbeddingDraft | null>(null)

  /** 拉取脱敏配置快照 */
  const load = async () => {
    try {
      const snap = await api.getSettings()
      setSnapshot(snap)
      // 用快照回填重排序 / 嵌入草稿（密钥留空，占位显示掩码）
      setReranker({
        enabled: snap.reranker.enabled,
        api_key: '',
        base_url: snap.reranker.base_url,
        model: snap.reranker.model,
        top_n: snap.reranker.top_n,
        candidate_k: snap.reranker.candidate_k,
      })
      setEmbedding({
        provider: snap.embedding.provider,
        api_key: '',
        base_url: snap.embedding.base_url,
        model: snap.embedding.model,
        dimension: snap.embedding.dimension,
      })
    } catch (e) {
      setError((e as ApiError).message)
    }
  }

  useEffect(() => {
    load()
  }, [])

  /** 获取/初始化某提供商的草稿 */
  const draftFor = (provider: string): LLMDraft =>
    llmDrafts[provider] ?? { api_key: '', base_url: '', model: '' }

  /** 更新某提供商草稿字段 */
  const setDraftField = (provider: string, field: keyof LLMDraft, value: string) => {
    setLlmDrafts((prev) => ({
      ...prev,
      [provider]: { ...draftFor(provider), [field]: value },
    }))
  }

  /** 保存某 LLM 提供商配置 */
  const saveLLM = async (provider: string) => {
    const d = draftFor(provider)
    setBusy(`llm:${provider}`)
    try {
      const snap = await api.updateLLMConfig(provider, {
        api_key: d.api_key || undefined,
        base_url: d.base_url || undefined,
        model: d.model || undefined,
      })
      setSnapshot(snap)
      // 清空本提供商的密钥草稿，避免残留明文
      setLlmDrafts((prev) => ({ ...prev, [provider]: { api_key: '', base_url: '', model: '' } }))
      message.success(`已保存 ${provider} 配置`)
    } catch (e) {
      message.error((e as ApiError).message)
    } finally {
      setBusy('')
    }
  }

  /** 切换默认提供商 */
  const setDefault = async (provider: string) => {
    setBusy(`default:${provider}`)
    try {
      setSnapshot(await api.updateDefaultProvider(provider))
      message.success(`默认模型已切换为 ${provider}`)
    } catch (e) {
      message.error((e as ApiError).message)
    } finally {
      setBusy('')
    }
  }

  /** 测试连通性 */
  const test = async (section: 'llm' | 'reranker', provider?: string) => {
    setBusy(`test:${section}:${provider ?? ''}`)
    try {
      const res = await api.testConnection({ section, provider })
      if (res.ok) message.success(res.message)
      else message.error(res.message)
    } catch (e) {
      message.error((e as ApiError).message)
    } finally {
      setBusy('')
    }
  }

  /** 保存重排序配置 */
  const saveReranker = async () => {
    if (!reranker) return
    setBusy('reranker')
    try {
      const snap = await api.updateRerankerConfig({
        enabled: reranker.enabled,
        api_key: reranker.api_key || undefined,
        base_url: reranker.base_url || undefined,
        model: reranker.model || undefined,
        top_n: reranker.top_n,
        candidate_k: reranker.candidate_k,
      })
      setSnapshot(snap)
      setReranker((r) => (r ? { ...r, api_key: '' } : r))
      message.success('重排序配置已保存')
    } catch (e) {
      message.error((e as ApiError).message)
    } finally {
      setBusy('')
    }
  }

  /** 保存嵌入配置 */
  const saveEmbedding = async () => {
    if (!embedding) return
    setBusy('embedding')
    try {
      const snap = await api.updateEmbeddingConfig({
        provider: embedding.provider || undefined,
        api_key: embedding.api_key || undefined,
        base_url: embedding.base_url || undefined,
        model: embedding.model || undefined,
        dimension: embedding.dimension,
      })
      setSnapshot(snap)
      setEmbedding((e2) => (e2 ? { ...e2, api_key: '' } : e2))
      message.success('嵌入配置已保存（若切换了模型/维度，请重新上传文档重建索引）')
    } catch (e) {
      message.error((e as ApiError).message)
    } finally {
      setBusy('')
    }
  }

  if (!snapshot) {
    return (
      <div>
        <h2 className="panel-title">系统设置</h2>
        {error ? (
          <Card>
            <span style={{ color: 'var(--danger)' }}>{error}</span>
          </Card>
        ) : (
          <div style={{ textAlign: 'center', padding: 60 }}>
            <Spin size="large" />
          </div>
        )}
      </div>
    )
  }

  return (
    <div>
      <h2 className="panel-title">系统设置</h2>
      <p className="panel-desc">
        在网页端完成大模型密钥的接入与切换，并管理嵌入与重排序服务。所有密钥均以掩码展示（脱密保护），
        真实密钥不会返回浏览器；输入框留空表示保持原有密钥不变。
      </p>

      {/* ---------------- LLM 提供商 ---------------- */}
      <Card
        title={
          <Space>
            <ApiOutlined /> 大模型接入（当前默认：{snapshot.default_provider}）
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        <Row gutter={16}>
          {snapshot.llm.map((p) => {
            const d = draftFor(p.provider)
            const isDefault = snapshot.default_provider === p.provider
            return (
              <Col xs={24} lg={12} key={p.provider}>
                <Card
                  size="small"
                  style={{ borderColor: isDefault ? 'var(--primary)' : undefined, marginBottom: 12 }}
                  title={
                    <Space>
                      <KeyOutlined /> {p.description}
                      {isDefault && <Tag color="purple">默认模型</Tag>}
                    </Space>
                  }
                  extra={
                    <Badge
                      status={p.available ? 'success' : 'error'}
                      text={p.available ? '已配置密钥' : '未配置密钥'}
                    />
                  }
                >
                  <FieldLabel>API Key</FieldLabel>
                  <Input.Password
                    placeholder={
                      p.has_key ? `已配置：${p.api_key_masked}（留空不修改）` : '未配置，请填写 API Key'
                    }
                    value={d.api_key}
                    onChange={(e) => setDraftField(p.provider, 'api_key', e.target.value)}
                  />
                  <FieldLabel>Base URL</FieldLabel>
                  <Input
                    placeholder={p.base_url || 'OpenAI 兼容端点'}
                    value={d.base_url}
                    onChange={(e) => setDraftField(p.provider, 'base_url', e.target.value)}
                  />
                  <FieldLabel>模型</FieldLabel>
                  <Input
                    placeholder={p.model || '模型名'}
                    value={d.model}
                    onChange={(e) => setDraftField(p.provider, 'model', e.target.value)}
                  />
                  <Space wrap style={{ marginTop: 12 }}>
                    <Button
                      type="primary"
                      icon={<CheckOutlined />}
                      onClick={() => saveLLM(p.provider)}
                      disabled={busy !== ''}
                      loading={busy === `llm:${p.provider}`}
                    >
                      保存
                    </Button>
                    <Button
                      icon={<ThunderboltOutlined />}
                      onClick={() => test('llm', p.provider)}
                      disabled={busy !== '' || !p.available}
                      loading={busy === `test:llm:${p.provider}`}
                    >
                      测试连通
                    </Button>
                    {!isDefault && (
                      <Button
                        onClick={() => setDefault(p.provider)}
                        disabled={busy !== '' || !p.available}
                        loading={busy === `default:${p.provider}`}
                      >
                        设为默认
                      </Button>
                    )}
                  </Space>
                </Card>
              </Col>
            )
          })}
        </Row>
      </Card>

      {/* ---------------- 重排序 ---------------- */}
      {reranker && (
        <Card
          title={
            <Space>
              <CloudServerOutlined /> 重排序（两阶段检索）
            </Space>
          }
          extra={
            <Space>
              <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>启用</span>
              <Switch
                checked={reranker.enabled}
                onChange={(v) => setReranker({ ...reranker, enabled: v })}
              />
            </Space>
          }
          style={{ marginBottom: 16 }}
        >
          <p className="panel-desc" style={{ marginBottom: 8 }}>
            开启后先由向量检索召回 candidate_k 条候选，再用重排序模型精排至 top_n 条，显著提升相关性；
            调用失败会自动降级为向量检索结果，不阻断问答。
          </p>
          <Row gutter={16}>
            <Col xs={24} lg={12}>
              <FieldLabel>API Key</FieldLabel>
              <Input.Password
                placeholder={
                  snapshot.reranker.has_key
                    ? `已配置：${snapshot.reranker.api_key_masked}（留空不修改）`
                    : '未配置，请填写 API Key'
                }
                value={reranker.api_key}
                onChange={(e) => setReranker({ ...reranker, api_key: e.target.value })}
              />
              <FieldLabel>Base URL</FieldLabel>
              <Input
                value={reranker.base_url}
                onChange={(e) => setReranker({ ...reranker, base_url: e.target.value })}
              />
              <FieldLabel>重排序模型</FieldLabel>
              <Input
                value={reranker.model}
                onChange={(e) => setReranker({ ...reranker, model: e.target.value })}
              />
            </Col>
            <Col xs={24} lg={12}>
              <FieldLabel>候选数 candidate_k（向量召回数量）</FieldLabel>
              <InputNumber
                style={{ width: '100%' }}
                min={1}
                value={reranker.candidate_k}
                onChange={(v) => setReranker({ ...reranker, candidate_k: v ?? 1 })}
              />
              <FieldLabel>精排数 top_n（最终返回数量）</FieldLabel>
              <InputNumber
                style={{ width: '100%' }}
                min={1}
                value={reranker.top_n}
                onChange={(v) => setReranker({ ...reranker, top_n: v ?? 1 })}
              />
            </Col>
          </Row>
          <Space style={{ marginTop: 12 }}>
            <Button
              type="primary"
              icon={<CheckOutlined />}
              onClick={saveReranker}
              disabled={busy !== ''}
              loading={busy === 'reranker'}
            >
              保存重排序
            </Button>
            <Button
              icon={<ThunderboltOutlined />}
              onClick={() => test('reranker')}
              disabled={busy !== '' || !snapshot.reranker.has_key}
              loading={busy === 'test:reranker:'}
            >
              测试连通
            </Button>
          </Space>
        </Card>
      )}

      {/* ---------------- 嵌入 ---------------- */}
      {embedding && (
        <Card
          title={
            <Space>
              <DatabaseOutlined /> 嵌入模型
            </Space>
          }
        >
          <p className="panel-desc" style={{ marginBottom: 8 }}>
            嵌入模型决定向量维度。切换模型或维度后与库内已有向量不一致时检索会返回空，需重新上传文档重建索引。
          </p>
          <Row gutter={16}>
            <Col xs={24} lg={12}>
              <FieldLabel>提供商</FieldLabel>
              <Input
                value={embedding.provider}
                onChange={(e) => setEmbedding({ ...embedding, provider: e.target.value })}
              />
              <FieldLabel>API Key</FieldLabel>
              <Input.Password
                placeholder={
                  snapshot.embedding.has_key
                    ? `已配置：${snapshot.embedding.api_key_masked}（留空不修改）`
                    : '未配置，请填写 API Key'
                }
                value={embedding.api_key}
                onChange={(e) => setEmbedding({ ...embedding, api_key: e.target.value })}
              />
            </Col>
            <Col xs={24} lg={12}>
              <FieldLabel>Base URL</FieldLabel>
              <Input
                value={embedding.base_url}
                onChange={(e) => setEmbedding({ ...embedding, base_url: e.target.value })}
              />
              <FieldLabel>模型</FieldLabel>
              <Input
                value={embedding.model}
                onChange={(e) => setEmbedding({ ...embedding, model: e.target.value })}
              />
              <FieldLabel>维度 dimension</FieldLabel>
              <InputNumber
                style={{ width: '100%' }}
                min={1}
                value={embedding.dimension}
                onChange={(v) => setEmbedding({ ...embedding, dimension: v ?? 1 })}
              />
            </Col>
          </Row>
          <Button
            type="primary"
            icon={<CheckOutlined />}
            onClick={saveEmbedding}
            disabled={busy !== ''}
            loading={busy === 'embedding'}
            style={{ marginTop: 12 }}
          >
            保存嵌入配置
          </Button>
        </Card>
      )}
    </div>
  )
}

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
import { api, ApiError } from '../api/client'
import type { SettingsSnapshot } from '../types'
import Icon from './Icon'

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

export default function SettingsPanel() {
  const [snapshot, setSnapshot] = useState<SettingsSnapshot | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
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

  /** 短暂提示 */
  const flash = (msg: string) => {
    setNotice(msg)
    window.setTimeout(() => setNotice(''), 2800)
  }

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
    setError('')
    try {
      const snap = await api.updateLLMConfig(provider, {
        api_key: d.api_key || undefined,
        base_url: d.base_url || undefined,
        model: d.model || undefined,
      })
      setSnapshot(snap)
      // 清空本提供商的密钥草稿，避免残留明文
      setLlmDrafts((prev) => ({ ...prev, [provider]: { api_key: '', base_url: '', model: '' } }))
      flash(`已保存 ${provider} 配置`)
    } catch (e) {
      setError((e as ApiError).message)
    } finally {
      setBusy('')
    }
  }

  /** 切换默认提供商 */
  const setDefault = async (provider: string) => {
    setBusy(`default:${provider}`)
    setError('')
    try {
      setSnapshot(await api.updateDefaultProvider(provider))
      flash(`默认模型已切换为 ${provider}`)
    } catch (e) {
      setError((e as ApiError).message)
    } finally {
      setBusy('')
    }
  }

  /** 测试连通性 */
  const test = async (section: 'llm' | 'reranker', provider?: string) => {
    setBusy(`test:${section}:${provider ?? ''}`)
    setError('')
    try {
      const res = await api.testConnection({ section, provider })
      if (res.ok) flash(res.message)
      else setError(res.message)
    } catch (e) {
      setError((e as ApiError).message)
    } finally {
      setBusy('')
    }
  }

  /** 保存重排序配置 */
  const saveReranker = async () => {
    if (!reranker) return
    setBusy('reranker')
    setError('')
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
      flash('重排序配置已保存')
    } catch (e) {
      setError((e as ApiError).message)
    } finally {
      setBusy('')
    }
  }

  /** 保存嵌入配置 */
  const saveEmbedding = async () => {
    if (!embedding) return
    setBusy('embedding')
    setError('')
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
      flash('嵌入配置已保存（若切换了模型/维度，请重新上传文档重建索引）')
    } catch (e) {
      setError((e as ApiError).message)
    } finally {
      setBusy('')
    }
  }

  if (!snapshot) {
    return (
      <div>
        <h2 className="panel-title">系统设置</h2>
        {error ? (
          <div className="alert error">
            <Icon name="alert" size={16} /> {error}
          </div>
        ) : (
          <div className="empty">加载配置中…</div>
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

      {error && (
        <div className="alert error">
          <Icon name="alert" size={16} /> {error}
        </div>
      )}
      {notice && (
        <div className="alert">
          <Icon name="check" size={16} /> {notice}
        </div>
      )}

      {/* ---------------- LLM 提供商 ---------------- */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-title">
          <Icon name="cpu" size={16} /> 大模型接入（当前默认：{snapshot.default_provider}）
        </div>
        <div className="grid-2" style={{ marginTop: 12 }}>
          {snapshot.llm.map((p) => {
            const d = draftFor(p.provider)
            const isDefault = snapshot.default_provider === p.provider
            return (
              <div
                key={p.provider}
                className="card"
                style={{ borderColor: isDefault ? 'var(--primary)' : undefined }}
              >
                <div
                  className="card-title"
                  style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                >
                  <span>
                    <Icon name="key" size={15} /> {p.description}
                  </span>
                  <span className={`status-dot ${p.available ? 'ok' : 'err'}`} title={p.available ? '已配置密钥' : '未配置密钥'} />
                </div>

                <label className="field-label">API Key</label>
                <input
                  style={{ width: '100%' }}
                  type="password"
                  placeholder={p.has_key ? `已配置：${p.api_key_masked}（留空不修改）` : '未配置，请填写 API Key'}
                  value={d.api_key}
                  onChange={(e) => setDraftField(p.provider, 'api_key', e.target.value)}
                />

                <label className="field-label">Base URL</label>
                <input
                  style={{ width: '100%' }}
                  placeholder={p.base_url || 'OpenAI 兼容端点'}
                  value={d.base_url}
                  onChange={(e) => setDraftField(p.provider, 'base_url', e.target.value)}
                />

                <label className="field-label">模型</label>
                <input
                  style={{ width: '100%' }}
                  placeholder={p.model || '模型名'}
                  value={d.model}
                  onChange={(e) => setDraftField(p.provider, 'model', e.target.value)}
                />

                <div className="toolbar" style={{ marginTop: 10 }}>
                  <button className="btn-primary" onClick={() => saveLLM(p.provider)} disabled={busy !== ''}>
                    <Icon name="check" size={14} /> {busy === `llm:${p.provider}` ? '保存中…' : '保存'}
                  </button>
                  <button className="btn-ghost" onClick={() => test('llm', p.provider)} disabled={busy !== '' || !p.available}>
                    <Icon name="activity" size={14} /> {busy === `test:llm:${p.provider}` ? '测试中…' : '测试连通'}
                  </button>
                  {!isDefault && (
                    <button className="btn-ghost" onClick={() => setDefault(p.provider)} disabled={busy !== '' || !p.available}>
                      <Icon name="check" size={14} /> 设为默认
                    </button>
                  )}
                  {isDefault && <span className="tag tool">默认模型</span>}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* ---------------- 重排序 ---------------- */}
      {reranker && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>
              <Icon name="layers" size={16} /> 重排序（两阶段检索）
            </span>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={reranker.enabled}
                onChange={(e) => setReranker({ ...reranker, enabled: e.target.checked })}
              />
              启用
            </label>
          </div>
          <p className="panel-desc" style={{ marginTop: 6 }}>
            开启后先由向量检索召回 candidate_k 条候选，再用重排序模型精排至 top_n 条，显著提升相关性；
            调用失败会自动降级为向量检索结果，不阻断问答。
          </p>

          <div className="grid-2" style={{ marginTop: 4 }}>
            <div>
              <label className="field-label">API Key</label>
              <input
                style={{ width: '100%' }}
                type="password"
                placeholder={snapshot.reranker.has_key ? `已配置：${snapshot.reranker.api_key_masked}（留空不修改）` : '未配置，请填写 API Key'}
                value={reranker.api_key}
                onChange={(e) => setReranker({ ...reranker, api_key: e.target.value })}
              />
              <label className="field-label">Base URL</label>
              <input
                style={{ width: '100%' }}
                value={reranker.base_url}
                onChange={(e) => setReranker({ ...reranker, base_url: e.target.value })}
              />
              <label className="field-label">重排序模型</label>
              <input
                style={{ width: '100%' }}
                value={reranker.model}
                onChange={(e) => setReranker({ ...reranker, model: e.target.value })}
              />
            </div>
            <div>
              <label className="field-label">候选数 candidate_k（向量召回数量）</label>
              <input
                style={{ width: '100%' }}
                type="number"
                min={1}
                value={reranker.candidate_k}
                onChange={(e) => setReranker({ ...reranker, candidate_k: Number(e.target.value) })}
              />
              <label className="field-label">精排数 top_n（最终返回数量）</label>
              <input
                style={{ width: '100%' }}
                type="number"
                min={1}
                value={reranker.top_n}
                onChange={(e) => setReranker({ ...reranker, top_n: Number(e.target.value) })}
              />
            </div>
          </div>

          <div className="toolbar" style={{ marginTop: 10 }}>
            <button className="btn-primary" onClick={saveReranker} disabled={busy !== ''}>
              <Icon name="check" size={14} /> {busy === 'reranker' ? '保存中…' : '保存重排序'}
            </button>
            <button className="btn-ghost" onClick={() => test('reranker')} disabled={busy !== '' || !snapshot.reranker.has_key}>
              <Icon name="activity" size={14} /> {busy === 'test:reranker:' ? '测试中…' : '测试连通'}
            </button>
          </div>
        </div>
      )}

      {/* ---------------- 嵌入 ---------------- */}
      {embedding && (
        <div className="card">
          <div className="card-title">
            <Icon name="database" size={16} /> 嵌入模型
          </div>
          <p className="panel-desc" style={{ marginTop: 6 }}>
            嵌入模型决定向量维度。切换模型或维度后与库内已有向量不一致时检索会返回空，需重新上传文档重建索引。
          </p>
          <div className="grid-2" style={{ marginTop: 4 }}>
            <div>
              <label className="field-label">提供商</label>
              <input
                style={{ width: '100%' }}
                value={embedding.provider}
                onChange={(e) => setEmbedding({ ...embedding, provider: e.target.value })}
              />
              <label className="field-label">API Key</label>
              <input
                style={{ width: '100%' }}
                type="password"
                placeholder={snapshot.embedding.has_key ? `已配置：${snapshot.embedding.api_key_masked}（留空不修改）` : '未配置，请填写 API Key'}
                value={embedding.api_key}
                onChange={(e) => setEmbedding({ ...embedding, api_key: e.target.value })}
              />
            </div>
            <div>
              <label className="field-label">Base URL</label>
              <input
                style={{ width: '100%' }}
                value={embedding.base_url}
                onChange={(e) => setEmbedding({ ...embedding, base_url: e.target.value })}
              />
              <label className="field-label">模型</label>
              <input
                style={{ width: '100%' }}
                value={embedding.model}
                onChange={(e) => setEmbedding({ ...embedding, model: e.target.value })}
              />
              <label className="field-label">维度 dimension</label>
              <input
                style={{ width: '100%' }}
                type="number"
                min={1}
                value={embedding.dimension}
                onChange={(e) => setEmbedding({ ...embedding, dimension: Number(e.target.value) })}
              />
            </div>
          </div>
          <div className="toolbar" style={{ marginTop: 10 }}>
            <button className="btn-primary" onClick={saveEmbedding} disabled={busy !== ''}>
              <Icon name="check" size={14} /> {busy === 'embedding' ? '保存中…' : '保存嵌入配置'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

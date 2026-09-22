/**
 * 嵌入集成面板（企业化）。
 *
 * 让管理员把知识库问答能力嵌入任意产品：
 *  - 知识库（租户）管理：创建、查看规模；
 *  - API 密钥管理：创建（明文仅此一次展示）/ 吊销 / 脱敏列表；
 *  - 嵌入代码生成器：选择密钥 + 知识库 + 外观，生成一行 <script> 集成代码，
 *    可一键复制或打开演示页预览。
 */
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { ApiKeyInfo, KnowledgeBase } from '../types'
import Icon from './Icon'

/** 脱敏密钥的占位（用于生成代码片段，真实密钥仅在创建时出现一次） */
const KEY_PLACEHOLDER = 'ak_live_…'

export default function EmbedPanel() {
  const [kbs, setKbs] = useState<KnowledgeBase[]>([])
  const [keys, setKeys] = useState<ApiKeyInfo[]>([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  // 新建知识库表单
  const [kbName, setKbName] = useState('')
  const [kbDesc, setKbDesc] = useState('')
  // 新建密钥表单
  const [keyName, setKeyName] = useState('')
  const [keyKb, setKeyKb] = useState('')
  // 刚创建的密钥明文（仅此一次可见）
  const [freshKey, setFreshKey] = useState('')

  // 代码片段定制项
  const [snipKb, setSnipKb] = useState('')
  const [snipTitle, setSnipTitle] = useState('智能助手')
  const [snipColor, setSnipColor] = useState('#4f46e5')
  const [snipPos, setSnipPos] = useState<'right' | 'left'>('right')

  const load = async () => {
    try {
      const [kbList, keyList] = await Promise.all([api.listKbs(), api.listKeys()])
      setKbs(kbList)
      setKeys(keyList)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  useEffect(() => {
    load()
  }, [])

  /** 生成嵌入代码片段 */
  const snippet = useMemo(() => {
    const origin = window.location.origin
    const attrs = [
      `src="${origin}/embed/widget.js"`,
      `data-key="${freshKey || KEY_PLACEHOLDER}"`,
      snipKb && `data-kb="${snipKb}"`,
      snipTitle !== '智能助手' && `data-title="${snipTitle}"`,
      snipColor !== '#4f46e5' && `data-color="${snipColor}"`,
      snipPos === 'left' && `data-position="left"`,
      'async',
    ].filter(Boolean)
    return `<script\n  ${attrs.join('\n  ')}\n></script>`
  }, [freshKey, snipKb, snipTitle, snipColor, snipPos])

  const demoUrl = useMemo(() => {
    return `/embed/demo${freshKey ? `?key=${encodeURIComponent(freshKey)}` : ''}`
  }, [freshKey])

  const copySnippet = async () => {
    try {
      await navigator.clipboard.writeText(snippet)
      setNotice('嵌入代码已复制到剪贴板')
      setTimeout(() => setNotice(''), 2500)
    } catch {
      setError('复制失败，请手动选择复制')
    }
  }

  const createKb = async () => {
    if (!kbName.trim()) return
    try {
      await api.createKb({ name: kbName.trim(), description: kbDesc.trim() })
      setKbName('')
      setKbDesc('')
      setNotice('知识库已创建')
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const createKey = async () => {
    if (!keyName.trim()) return
    try {
      const res = await api.createKey({
        name: keyName.trim(),
        scopes: ['ask'],
        kb_id: keyKb || undefined,
      })
      setFreshKey(res.raw_key)
      setKeyName('')
      setNotice('密钥已创建，请立即保存——明文只显示这一次')
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const revokeKey = async (id: string) => {
    try {
      await api.revokeKey(id)
      setNotice('密钥已吊销')
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <div>
      <h2 className="panel-title">嵌入集成</h2>
      <p className="panel-desc">
        把知识库问答能力嵌入任意产品：创建知识库隔离数据 → 签发 API 密钥 → 一行 script 接入。
        公共问答接口走 <code>/api/v1</code>，密钥可绑定知识库实现租户隔离。
      </p>

      {error && (
        <div className="alert error">
          <Icon name="alert" size={16} /> {error}
        </div>
      )}
      {notice && (
        <div className="alert success">
          <Icon name="check" size={16} /> {notice}
        </div>
      )}

      <div className="grid-2">
        {/* ---------- 知识库管理 ---------- */}
        <div className="card">
          <div className="card-title">
            <Icon name="book" size={16} /> 知识库
          </div>
          <div className="list" style={{ marginTop: 12 }}>
            {kbs.map((kb) => (
              <div key={kb.kb_id} className="doc-item">
                <div>
                  <div className="doc-name">{kb.name}</div>
                  <div className="meta">
                    {kb.kb_id} · {kb.document_count} 篇文档 · {kb.chunk_count} 个片段
                  </div>
                </div>
                {kb.kb_id === 'default' && <span className="tag">内置</span>}
              </div>
            ))}
          </div>
          <div style={{ marginTop: 14 }}>
            <label className="field-label">名称</label>
            <input
              value={kbName}
              onChange={(e) => setKbName(e.target.value)}
              placeholder="如：客服知识库、产品手册"
              style={{ width: '100%' }}
            />
            <label className="field-label">描述（可选）</label>
            <input
              value={kbDesc}
              onChange={(e) => setKbDesc(e.target.value)}
              placeholder="这个知识库存什么内容"
              style={{ width: '100%' }}
            />
            <button
              className="btn-primary"
              style={{ marginTop: 12 }}
              onClick={createKb}
              disabled={!kbName.trim()}
            >
              <Icon name="plus" size={14} /> 创建知识库
            </button>
          </div>
        </div>

        {/* ---------- API 密钥管理 ---------- */}
        <div className="card">
          <div className="card-title">
            <Icon name="key" size={16} /> API 密钥
          </div>
          <div className="list" style={{ marginTop: 12 }}>
            {keys.length === 0 && <div className="empty">还没有密钥，先创建一个</div>}
            {keys.map((k) => (
              <div key={k.key_id} className="doc-item">
                <div>
                  <div className="doc-name">
                    {k.name}
                    {k.revoked && <span className="tag warn">已吊销</span>}
                  </div>
                  <div className="meta">
                    <code>{k.key_prefix}</code>
                    {' · '}
                    {k.kb_id ? `绑定 ${k.kb_id}` : '全部知识库'}
                    {k.last_used_at &&
                      ` · 最近使用 ${new Date(k.last_used_at * 1000).toLocaleString()}`}
                  </div>
                </div>
                {!k.revoked && (
                  <button className="btn-danger" onClick={() => revokeKey(k.key_id)}>
                    吊销
                  </button>
                )}
              </div>
            ))}
          </div>
          <div style={{ marginTop: 14 }}>
            <label className="field-label">密钥名称</label>
            <input
              value={keyName}
              onChange={(e) => setKeyName(e.target.value)}
              placeholder="如：官网挂件、App 生产环境"
              style={{ width: '100%' }}
            />
            <label className="field-label">绑定知识库（可选，绑定后仅可查该库）</label>
            <select
              value={keyKb}
              onChange={(e) => setKeyKb(e.target.value)}
              style={{ width: '100%' }}
            >
              <option value="">不绑定（可查全部知识库）</option>
              {kbs.map((kb) => (
                <option key={kb.kb_id} value={kb.kb_id}>
                  {kb.name}（{kb.kb_id}）
                </option>
              ))}
            </select>
            <button
              className="btn-primary"
              style={{ marginTop: 12 }}
              onClick={createKey}
              disabled={!keyName.trim()}
            >
              <Icon name="plus" size={14} /> 签发密钥
            </button>
          </div>
        </div>
      </div>

      {/* ---------- 新密钥明文（仅此一次） ---------- */}
      {freshKey && (
        <div className="card" style={{ borderColor: 'var(--warning)' }}>
          <div className="card-title">
            <Icon name="key" size={16} /> 新密钥（只显示这一次，请立即保存）
          </div>
          <div className="code-block" style={{ marginTop: 10, userSelect: 'all' }}>
            {freshKey}
          </div>
        </div>
      )}

      {/* ---------- 嵌入代码生成器 ---------- */}
      <div className="card">
        <div className="card-title">
          <Icon name="code" size={16} /> 嵌入代码生成器
        </div>
        <p className="panel-desc" style={{ marginTop: 8, marginBottom: 14 }}>
          把下面代码粘到目标网页的 <code>&lt;body&gt;</code> 任意位置即可。挂件为纯原生 JS +
          Shadow DOM，与宿主页面样式完全隔离、零依赖。
        </p>
        <div className="toolbar">
          <label>
            知识库：
            <select value={snipKb} onChange={(e) => setSnipKb(e.target.value)}>
              <option value="">默认（随密钥）</option>
              {kbs.map((kb) => (
                <option key={kb.kb_id} value={kb.kb_id}>
                  {kb.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            标题：
            <input
              value={snipTitle}
              onChange={(e) => setSnipTitle(e.target.value)}
              style={{ width: 120 }}
            />
          </label>
          <label>
            主题色：
            <input
              type="color"
              value={snipColor}
              onChange={(e) => setSnipColor(e.target.value)}
              style={{ width: 42, padding: 4, height: 34 }}
            />
          </label>
          <label>
            位置：
            <select
              value={snipPos}
              onChange={(e) => setSnipPos(e.target.value as 'right' | 'left')}
            >
              <option value="right">右下角</option>
              <option value="left">左下角</option>
            </select>
          </label>
        </div>
        <div className="code-block">{snippet}</div>
        <div className="toolbar" style={{ marginTop: 12, marginBottom: 0 }}>
          <button className="btn-primary" onClick={copySnippet}>
            <Icon name="copy" size={14} /> 复制代码
          </button>
          <a
            className="btn-ghost"
            href={demoUrl}
            target="_blank"
            rel="noreferrer"
            style={{ textDecoration: 'none' }}
          >
            <Icon name="external" size={14} /> 打开演示页
            {freshKey ? '（已带密钥）' : ''}
          </a>
          {!freshKey && (
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              提示：演示页支持 <code>?key=ak_live_xxx</code> 参数直接预览
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

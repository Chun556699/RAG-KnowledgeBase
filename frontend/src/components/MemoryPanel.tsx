/**
 * 记忆管理面板。
 *
 * 展示上下文记忆的四类能力：
 *  - 会话管理：列出历史会话，点击查看多轮消息，可删除；
 *  - 历史检索：按关键词跨会话检索消息内容；
 *  - 长期记忆：写入/查看持久化的键值偏好信息（附主题与重要度）；
 *  - 记忆清理：触发过期数据（TTL）自动清理。
 */
import { useEffect, useState } from 'react'
import { api, ApiError } from '../api/client'
import type { ChatMessage, LongTermItem, SessionInfo } from '../types'
import Icon from './Icon'

export default function MemoryPanel() {
  const [sessions, setSessions] = useState<SessionInfo[]>([])
  const [activeSession, setActiveSession] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [keyword, setKeyword] = useState('')
  const [searchResults, setSearchResults] = useState<ChatMessage[]>([])
  const [longTerm, setLongTerm] = useState<LongTermItem[]>([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  // 长期记忆写入表单
  const [ltKey, setLtKey] = useState('')
  const [ltValue, setLtValue] = useState('')
  const [ltTopic, setLtTopic] = useState('')
  const [ltImportance, setLtImportance] = useState(3)

  /** 加载会话与长期记忆列表 */
  const refresh = async () => {
    try {
      const [s, lt] = await Promise.all([api.listSessions(), api.listLongTerm()])
      setSessions(s)
      setLongTerm(lt)
    } catch (e) {
      setError((e as ApiError).message)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  /** 查看某会话的完整消息 */
  const openSession = async (id: string) => {
    setActiveSession(id)
    setError('')
    try {
      setMessages(await api.getMessages(id))
    } catch (e) {
      setError((e as ApiError).message)
    }
  }

  /** 删除会话 */
  const removeSession = async (id: string) => {
    try {
      await api.deleteSession(id)
      if (activeSession === id) {
        setActiveSession(null)
        setMessages([])
      }
      await refresh()
    } catch (e) {
      setError((e as ApiError).message)
    }
  }

  /** 关键词检索历史 */
  const search = async () => {
    const k = keyword.trim()
    if (!k) return
    setError('')
    try {
      setSearchResults(await api.searchHistory(k))
    } catch (e) {
      setError((e as ApiError).message)
    }
  }

  /** 写入长期记忆 */
  const remember = async () => {
    if (!ltKey.trim() || !ltValue.trim()) return
    setError('')
    setNotice('')
    try {
      await api.remember({
        key: ltKey.trim(),
        value: ltValue.trim(),
        topic: ltTopic.trim() || undefined,
        importance: ltImportance,
      })
      setNotice('已写入长期记忆。')
      setLtKey('')
      setLtValue('')
      setLtTopic('')
      await refresh()
    } catch (e) {
      setError((e as ApiError).message)
    }
  }

  /** 触发过期清理 */
  const cleanup = async () => {
    setError('')
    setNotice('')
    try {
      const res = await api.cleanupMemory()
      setNotice(res.message)
      await refresh()
    } catch (e) {
      setError((e as ApiError).message)
    }
  }

  return (
    <div>
      <h2 className="panel-title">记忆管理</h2>
      <p className="panel-desc">
        维护多轮会话上下文、跨会话历史检索、持久化长期记忆，并支持过期数据自动清理。
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

      <div className="toolbar">
        <button className="btn-ghost" onClick={refresh}>
          <Icon name="refresh" size={15} /> 刷新
        </button>
        <button className="btn-ghost" onClick={cleanup}>
          <Icon name="broom" size={15} /> 清理过期记忆
        </button>
      </div>

      <div className="grid-2">
        {/* 会话列表 + 详情 */}
        <div className="card">
          <div className="card-title">
            <Icon name="message" size={16} /> 会话列表（{sessions.length}）
          </div>
          {sessions.length === 0 ? (
            <div className="empty">暂无会话，去"智能对话"发起一次吧。</div>
          ) : (
            <div className="list" style={{ marginTop: 10 }}>
              {sessions.map((s) => (
                <div key={s.id} className="doc-item">
                  <div style={{ cursor: 'pointer' }} onClick={() => openSession(s.id)}>
                    <div>{s.title || '未命名会话'}</div>
                    <div className="meta">
                      {new Date(s.updated_at * 1000).toLocaleString()}
                      {activeSession === s.id ? ' · 查看中' : ''}
                    </div>
                  </div>
                  <button className="btn-danger" onClick={() => removeSession(s.id)}>
                    删除
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* 选中会话的消息 */}
          {activeSession && (
            <div style={{ marginTop: 14 }}>
              <strong>会话内容</strong>
              <div className="list" style={{ marginTop: 8 }}>
                {messages.map((m, i) => (
                  <div key={i} className="code-block">
                    <span className="tag">{m.role}</span> {m.content}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* 历史检索 + 长期记忆 */}
        <div>
          <div className="card">
            <div className="card-title">
              <Icon name="search" size={16} /> 历史检索
            </div>
            <div className="toolbar" style={{ marginTop: 10 }}>
              <input
                style={{ flex: 1 }}
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && search()}
                placeholder="按关键词检索历史消息…"
              />
              <button className="btn-primary" onClick={search}>
                检索
              </button>
            </div>
            {searchResults.length > 0 && (
              <div className="list" style={{ marginTop: 10 }}>
                {searchResults.map((m, i) => (
                  <div key={i} className="code-block">
                    <span className="tag">{m.role}</span> {m.content}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="card">
            <div className="card-title">
              <Icon name="bookmark" size={16} /> 长期记忆
            </div>
            {/* 写入表单 */}
            <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
              <input value={ltKey} onChange={(e) => setLtKey(e.target.value)} placeholder="键（如：用户偏好语言）" />
              <input value={ltValue} onChange={(e) => setLtValue(e.target.value)} placeholder="值（如：中文）" />
              <div className="toolbar" style={{ margin: 0 }}>
                <input
                  style={{ flex: 1 }}
                  value={ltTopic}
                  onChange={(e) => setLtTopic(e.target.value)}
                  placeholder="主题（可选）"
                />
                <select value={ltImportance} onChange={(e) => setLtImportance(Number(e.target.value))}>
                  {[1, 2, 3, 4, 5].map((n) => (
                    <option key={n} value={n}>
                      重要度 {n}
                    </option>
                  ))}
                </select>
                <button className="btn-primary" onClick={remember}>
                  记住
                </button>
              </div>
            </div>

            {/* 长期记忆列表 */}
            {longTerm.length === 0 ? (
              <div className="empty">暂无长期记忆。</div>
            ) : (
              <div className="list" style={{ marginTop: 12 }}>
                {longTerm.map((it) => (
                  <div key={it.id} className="doc-item">
                    <div>
                      <div>
                        <strong>{it.key}</strong>：{it.value}
                      </div>
                      <div className="meta">
                        {it.topic && <span className="tag">{it.topic}</span>} 重要度 {it.importance}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

/**
 * 智能对话面板（RAG）。
 *
 * 展示"检索增强生成"的完整流程：
 *  - 用户提问后，可选择是否启用知识库检索（use_rag）；
 *  - 通过 SSE 流式接收模型回答，实现打字机式实时反馈；
 *  - 回答下方展示本次引用的知识库来源片段与相似度分数；
 *  - 维护多轮会话上下文（session_id 由后端下发后固定）。
 */
import { useEffect, useRef, useState } from 'react'
import { chatStream } from '../api/client'
import type { ChatMessage, Clarify, RetrievedChunk, SelectedModel } from '../types'
import Icon from './Icon'

interface Props {
  /** 当前选中的模型（来自全局选择器） */
  model: SelectedModel | null
}

export default function ChatPanel({ model }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [useRag, setUseRag] = useState(true)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [sessionId, setSessionId] = useState<string | undefined>(undefined)
  // 待澄清标记：上一条助手回复为反问时置位，使下一轮回应直接作答、不再重复反问
  const [clarifyPending, setClarifyPending] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // 消息变化时自动滚动到底部，保证最新内容可见
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  /**
   * 发送一条消息并以流式方式接收回答。
   *
   * @param textArg 可选的消息文本（点击澄清候选项时传入）；缺省取输入框内容。
   * @param opts.allowClarify 是否允许本轮反问澄清；回应澄清时传 false。
   */
  const send = async (textArg?: string, opts?: { allowClarify?: boolean }) => {
    const text = (textArg ?? input).trim()
    if (!text || sending) return
    setError('')
    setSending(true)
    setInput('')

    // 默认：若上一条为反问，则本轮为回应澄清，不再反问；否则允许反问
    const allowClarify = opts?.allowClarify ?? !clarifyPending
    if (clarifyPending) setClarifyPending(false)

    // 立即插入用户消息，以及一个空的助手占位消息（用于流式填充）
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: text },
      { role: 'assistant', content: '', sources: [] },
    ])

    // 助手消息在数组中的索引（当前最后一条）
    const assistantIndex = messages.length + 1

    await chatStream(
      {
        message: text,
        session_id: sessionId,
        provider: model?.provider,
        model: model?.model,
        use_rag: useRag,
        allow_clarify: allowClarify,
      },
      {
        // 元信息：固定会话 ID，并把来源挂到助手消息上
        onMeta: (meta) => {
          setSessionId(meta.session_id)
          setMessages((prev) => {
            const next = [...prev]
            if (next[assistantIndex]) {
              next[assistantIndex] = {
                ...next[assistantIndex],
                sources: meta.sources,
              }
            }
            return next
          })
        },
        // 反问澄清：把澄清问题作为助手正文，并携带候选方向供一键选择
        onClarify: (clarify: Clarify) => {
          setClarifyPending(true)
          setMessages((prev) => {
            const next = [...prev]
            if (next[assistantIndex]) {
              next[assistantIndex] = {
                ...next[assistantIndex],
                content: clarify.question,
                clarify,
              }
            }
            return next
          })
        },
        // 文本增量：追加到助手消息内容
        onDelta: (delta) => {
          setMessages((prev) => {
            const next = [...prev]
            if (next[assistantIndex]) {
              next[assistantIndex] = {
                ...next[assistantIndex],
                content: next[assistantIndex].content + delta,
              }
            }
            return next
          })
        },
        onDone: () => setSending(false),
        onError: (err) => {
          setError(err.message)
          setSending(false)
        },
      },
    )
  }

  /** 回车发送，Shift+Enter 换行 */
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  /** 空状态引导：点击即填入输入框 */
  const suggestions = [
    '用一句话概括我上传的文档核心内容',
    '知识库里关于向量检索的要点有哪些？',
    '介绍一下 RAG 的工作流程',
  ]

  /** 渲染单条消息的来源片段 */
  const renderSources = (sources?: RetrievedChunk[]) => {
    if (!sources || sources.length === 0) return null
    return (
      <div className="sources">
        <div className="sources-head">
          <Icon name="link" size={14} /> 参考来源（{sources.length}）
        </div>
        {sources.map((s, i) => (
          <div key={i} className="source-item">
            <span className="tag">{s.filename}</span>{' '}
            <span className="tag score">相似度 {(s.score * 100).toFixed(1)}%</span>{' '}
            {s.text.slice(0, 80)}…
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="chat-container">
      <h2 className="panel-title">智能对话</h2>
      <p className="panel-desc">
        基于检索增强生成（RAG）的多轮问答。问题模糊时助手会先反问澄清、给出候选方向，可一键选择。
      </p>

      {error && (
        <div className="alert error">
          <Icon name="alert" size={16} /> {error}
        </div>
      )}

      {/* 消息列表 */}
      <div className="messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <div className="chat-empty-icon">
              <Icon name="message" size={30} strokeWidth={1.5} />
            </div>
            <div className="chat-empty-title">开始一段对话</div>
            <div className="chat-empty-desc">
              开启“知识库检索”后，回答会引用你上传的文档内容。试试下面的问题：
            </div>
            <div className="suggestions">
              {suggestions.map((s, i) => (
                <button key={i} className="suggestion-chip" onClick={() => setInput(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`message ${m.role}`}>
            <div className="avatar">
              <Icon name={m.role === 'user' ? 'user' : 'bot'} size={18} />
            </div>
            <div className="bubble">
              {m.role === 'assistant' && m.clarify && (
                <div className="clarify-hint">
                  <Icon name="help" size={13} /> 需要你补充一下
                </div>
              )}
              {m.content || (sending && i === messages.length - 1 ? <span className="spinner" /> : '')}
              {m.role === 'assistant' && m.clarify && m.clarify.options.length > 0 && (
                <div className="clarify-options">
                  {m.clarify.options.map((opt, k) => (
                    <button
                      key={k}
                      className="clarify-chip"
                      onClick={() => send(opt, { allowClarify: false })}
                      disabled={sending}
                    >
                      {opt}
                    </button>
                  ))}
                </div>
              )}
              {m.role === 'assistant' && renderSources(m.sources)}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* 选项 + 输入区 */}
      <div>
        <div className="chat-options">
          <label>
            <input
              type="checkbox"
              checked={useRag}
              onChange={(e) => setUseRag(e.target.checked)}
            />
            启用知识库检索（RAG）
          </label>
          {sessionId && <span className="tag">会话：{sessionId.slice(0, 8)}</span>}
        </div>
        <div className="chat-input-row">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入你的问题，Enter 发送，Shift+Enter 换行…"
            disabled={sending}
          />
          <button className="btn-primary" onClick={() => send()} disabled={sending || !input.trim()}>
            <Icon name="send" size={15} /> {sending ? '生成中…' : '发送'}
          </button>
        </div>
      </div>
    </div>
  )
}

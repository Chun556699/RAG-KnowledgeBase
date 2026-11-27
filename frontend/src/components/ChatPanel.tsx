import { useEffect, useRef, useState } from 'react'
import { Alert, Avatar, Button, Card, Checkbox, Input, Space, Spin, Tag, Typography } from 'antd'
import BranchesOutlined from '@ant-design/icons/BranchesOutlined'
import LinkOutlined from '@ant-design/icons/LinkOutlined'
import RobotOutlined from '@ant-design/icons/RobotOutlined'
import SendOutlined from '@ant-design/icons/SendOutlined'
import UserOutlined from '@ant-design/icons/UserOutlined'
import { chatStream } from '../api/client'
import type { ChatMessage, Clarify, SelectedModel } from '../types'

const { TextArea } = Input
const suggestions = [
  '用一句话概括我上传的文档核心内容',
  '知识库里关于向量检索的要点有哪些？',
  '介绍一下 RAG 的工作流程',
]

export default function ChatPanel({ model }: { model: SelectedModel | null }) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [useRag, setUseRag] = useState(true)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [sessionId, setSessionId] = useState<string>()
  const [clarifyPending, setClarifyPending] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const patchAssistant = (index: number, patch: Partial<ChatMessage>) => {
    setMessages((prev) => prev.map((item, i) => i === index ? { ...item, ...patch } : item))
  }

  const send = async (textArg?: string, opts?: { allowClarify?: boolean }) => {
    const text = (textArg ?? input).trim()
    if (!text || sending) return
    setError('')
    setSending(true)
    setInput('')
    const allowClarify = opts?.allowClarify ?? !clarifyPending
    if (clarifyPending) setClarifyPending(false)

    const assistantIndex = messages.length + 1
    setMessages((prev) => [...prev, { role: 'user', content: text }, { role: 'assistant', content: '', sources: [], graph_triples: [] }])

    await chatStream(
      { message: text, session_id: sessionId, provider: model?.provider, model: model?.model, use_rag: useRag, allow_clarify: allowClarify },
      {
        onMeta: (meta) => {
          setSessionId(meta.session_id)
          patchAssistant(assistantIndex, { sources: meta.sources, graph_triples: meta.graph_triples })
        },
        onClarify: (clarify: Clarify) => {
          setClarifyPending(true)
          patchAssistant(assistantIndex, { content: clarify.question, clarify })
        },
        onDelta: (delta) => setMessages((prev) => prev.map((item, i) => i === assistantIndex ? { ...item, content: item.content + delta } : item)),
        onDone: () => setSending(false),
        onError: (err) => {
          setError(err.message)
          setSending(false)
          setMessages((prev) => prev.filter((_, i) => i !== assistantIndex || prev[i]?.content))
        },
      },
    )
  }

  return (
    <div className="chat-workspace">
      <div className="page-header" style={{ marginBottom: 0 }}>
        <div>
          <h2 className="page-title">智能对话</h2>
          <p className="page-description">面向企业知识库的流式问答，支持引用追溯、图谱增强与反问澄清。</p>
        </div>
        <Space wrap>
          <Checkbox checked={useRag} onChange={(e) => setUseRag(e.target.checked)}>启用知识库检索</Checkbox>
          {sessionId && <Tag color="blue">会话 {sessionId.slice(0, 8)}</Tag>}
        </Space>
      </div>

      <div className="chat-messages">
        {error && <Alert style={{ marginBottom: 14 }} type="error" showIcon message="请求失败" description={error} closable onClose={() => setError('')} />}
        {messages.length === 0 ? (
          <div className="chat-hero" style={{ margin: 'auto 0' }}>
            <Typography.Title level={2}>开始一段高质量知识问答</Typography.Title>
            <Typography.Paragraph>上传文档后，回答会基于可追溯来源生成；问题模糊时系统会先澄清意图。</Typography.Paragraph>
            <div className="suggestion-grid">
              {suggestions.map((item) => <div key={item} className="suggestion-card" onClick={() => setInput(item)}>{item}</div>)}
            </div>
          </div>
        ) : messages.map((message, index) => (
          <div key={index} className={`message-row ${message.role}`}>
            {message.role === 'assistant' && <Avatar style={{ marginRight: 10, background: '#4f63ff', flexShrink: 0 }} icon={<RobotOutlined />} />}
            <div className="message-bubble">
              {message.content || (sending && index === messages.length - 1 ? <Spin size="small" /> : '')}
              {message.clarify && (
                <div style={{ marginTop: 10 }}>
                  <Space wrap>{message.clarify.options.map((opt) => <Button key={opt} size="small" onClick={() => send(opt, { allowClarify: false })} disabled={sending}>{opt}</Button>)}</Space>
                </div>
              )}
              {message.graph_triples?.length ? (
                <div className="message-meta"><Tag icon={<BranchesOutlined />} color="cyan">图谱关系 {message.graph_triples.length}</Tag>{message.graph_triples.slice(0, 3).map((t, i) => <Tag key={i}>{t.source} → {t.relation} → {t.target}</Tag>)}</div>
              ) : null}
              {message.sources?.length ? (
                <div className="message-meta"><Tag icon={<LinkOutlined />} color="blue">参考来源 {message.sources.length}</Tag>{message.sources.slice(0, 3).map((s, i) => <Tag key={i}>{s.filename} · {(s.score * 100).toFixed(0)}%</Tag>)}</div>
              ) : null}
            </div>
            {message.role === 'user' && <Avatar style={{ marginLeft: 10, background: '#0f172a', flexShrink: 0 }} icon={<UserOutlined />} />}
          </div>
        ))}
        <div ref={endRef} />
      </div>

      <Card className="chat-composer" bordered={false}>
        <Space.Compact style={{ width: '100%' }} className="composer-input">
          <TextArea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
            placeholder="输入你的问题，Enter 发送，Shift+Enter 换行…"
            autoSize={{ minRows: 2, maxRows: 7 }}
            disabled={sending}
          />
          <Button type="primary" icon={<SendOutlined />} onClick={() => send()} disabled={sending || !input.trim()} style={{ height: 'auto', minWidth: 104 }}>
            {sending ? '生成中' : '发送'}
          </Button>
        </Space.Compact>
      </Card>
    </div>
  )
}

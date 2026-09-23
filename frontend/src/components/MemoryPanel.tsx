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
import {
  App,
  Button,
  Card,
  Col,
  Empty,
  Input,
  List,
  Popconfirm,
  Row,
  Select,
  Space,
  Tag,
} from 'antd'
import {
  ClearOutlined,
  DeleteOutlined,
  MessageOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import { api, ApiError } from '../api/client'
import type { ChatMessage, LongTermItem, SessionInfo } from '../types'

export default function MemoryPanel() {
  const { message } = App.useApp()
  const [sessions, setSessions] = useState<SessionInfo[]>([])
  const [activeSession, setActiveSession] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [keyword, setKeyword] = useState('')
  const [searchResults, setSearchResults] = useState<ChatMessage[]>([])
  const [longTerm, setLongTerm] = useState<LongTermItem[]>([])

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
      message.error((e as ApiError).message)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  /** 查看某会话的完整消息 */
  const openSession = async (id: string) => {
    setActiveSession(id)
    try {
      setMessages(await api.getMessages(id))
    } catch (e) {
      message.error((e as ApiError).message)
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
      message.success('会话已删除')
      await refresh()
    } catch (e) {
      message.error((e as ApiError).message)
    }
  }

  /** 关键词检索历史 */
  const search = async () => {
    const k = keyword.trim()
    if (!k) return
    try {
      setSearchResults(await api.searchHistory(k))
    } catch (e) {
      message.error((e as ApiError).message)
    }
  }

  /** 写入长期记忆 */
  const remember = async () => {
    if (!ltKey.trim() || !ltValue.trim()) return
    try {
      await api.remember({
        key: ltKey.trim(),
        value: ltValue.trim(),
        topic: ltTopic.trim() || undefined,
        importance: ltImportance,
      })
      message.success('已写入长期记忆')
      setLtKey('')
      setLtValue('')
      setLtTopic('')
      await refresh()
    } catch (e) {
      message.error((e as ApiError).message)
    }
  }

  /** 触发过期清理 */
  const cleanup = async () => {
    try {
      const res = await api.cleanupMemory()
      message.success(res.message)
      await refresh()
    } catch (e) {
      message.error((e as ApiError).message)
    }
  }

  return (
    <div>
      <h2 className="panel-title">记忆管理</h2>
      <p className="panel-desc">
        维护多轮会话上下文、跨会话历史检索、持久化长期记忆，并支持过期数据自动清理。
      </p>

      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ReloadOutlined />} onClick={refresh}>
          刷新
        </Button>
        <Popconfirm title="清理所有过期记忆？" onConfirm={cleanup} okText="清理" cancelText="取消">
          <Button icon={<ClearOutlined />}>清理过期记忆</Button>
        </Popconfirm>
      </Space>

      <Row gutter={16}>
        {/* 会话列表 + 详情 */}
        <Col xs={24} lg={12}>
          <Card
            title={
              <Space>
                <MessageOutlined /> 会话列表（{sessions.length}）
              </Space>
            }
          >
            {sessions.length === 0 ? (
              <Empty description='暂无会话，去"智能对话"发起一次吧' />
            ) : (
              <List
                size="small"
                dataSource={sessions}
                renderItem={(s) => (
                  <List.Item
                    style={{ cursor: 'pointer' }}
                    onClick={() => openSession(s.id)}
                    actions={[
                      <Popconfirm
                        key="del"
                        title="删除该会话及其消息？"
                        okText="删除"
                        cancelText="取消"
                        okButtonProps={{ danger: true }}
                        onConfirm={(e) => {
                          e?.stopPropagation()
                          removeSession(s.id)
                        }}
                      >
                        <Button
                          type="text"
                          danger
                          size="small"
                          icon={<DeleteOutlined />}
                          onClick={(e) => e.stopPropagation()}
                        />
                      </Popconfirm>,
                    ]}
                  >
                    <List.Item.Meta
                      title={
                        <span>
                          {s.title || '未命名会话'}
                          {activeSession === s.id && (
                            <Tag color="processing" style={{ marginLeft: 6 }}>
                              查看中
                            </Tag>
                          )}
                        </span>
                      }
                      description={new Date(s.updated_at * 1000).toLocaleString()}
                    />
                  </List.Item>
                )}
              />
            )}

            {/* 选中会话的消息 */}
            {activeSession && (
              <div style={{ marginTop: 14 }}>
                <strong>会话内容</strong>
                <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {messages.map((m, i) => (
                    <div key={i} className="code-block">
                      <Tag>{m.role}</Tag> {m.content}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </Card>
        </Col>

        {/* 历史检索 + 长期记忆 */}
        <Col xs={24} lg={12}>
          <Card
            title={
              <Space>
                <SearchOutlined /> 历史检索
              </Space>
            }
            style={{ marginBottom: 16 }}
          >
            <Space.Compact style={{ width: '100%' }}>
              <Input
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                onPressEnter={search}
                placeholder="按关键词检索历史消息…"
              />
              <Button type="primary" onClick={search}>
                检索
              </Button>
            </Space.Compact>
            {searchResults.length > 0 && (
              <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
                {searchResults.map((m, i) => (
                  <div key={i} className="code-block">
                    <Tag>{m.role}</Tag> {m.content}
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card title="长期记忆">
            {/* 写入表单 */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <Input
                value={ltKey}
                onChange={(e) => setLtKey(e.target.value)}
                placeholder="键（如：用户偏好语言）"
              />
              <Input
                value={ltValue}
                onChange={(e) => setLtValue(e.target.value)}
                placeholder="值（如：中文）"
              />
              <Space>
                <Input
                  style={{ flex: 1 }}
                  value={ltTopic}
                  onChange={(e) => setLtTopic(e.target.value)}
                  placeholder="主题（可选）"
                />
                <Select
                  style={{ width: 120 }}
                  value={ltImportance}
                  options={[1, 2, 3, 4, 5].map((n) => ({ value: n, label: `重要度 ${n}` }))}
                  onChange={setLtImportance}
                />
                <Button type="primary" onClick={remember}>
                  记住
                </Button>
              </Space>
            </div>

            {/* 长期记忆列表 */}
            {longTerm.length === 0 ? (
              <Empty description="暂无长期记忆" style={{ marginTop: 16 }} />
            ) : (
              <List
                size="small"
                style={{ marginTop: 12 }}
                dataSource={longTerm}
                renderItem={(it) => (
                  <List.Item>
                    <List.Item.Meta
                      title={
                        <span>
                          <strong>{it.key}</strong>：{it.value}
                        </span>
                      }
                      description={
                        <Space>
                          {it.topic && <Tag>{it.topic}</Tag>}
                          <span style={{ fontSize: 12 }}>重要度 {it.importance}</span>
                        </Space>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}

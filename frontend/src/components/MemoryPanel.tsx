import { useEffect, useState } from 'react'
import { App, Button, Card, Col, Empty, Form, Input, List, Modal, Popconfirm, Row, Select, Slider, Space, Table, Tabs, Tag, Typography } from 'antd'
import ClearOutlined from '@ant-design/icons/ClearOutlined'
import DeleteOutlined from '@ant-design/icons/DeleteOutlined'
import PlusOutlined from '@ant-design/icons/PlusOutlined'
import SearchOutlined from '@ant-design/icons/SearchOutlined'
import type { ColumnsType } from 'antd/es/table'
import { api } from '../api/client'
import type { ChatMessage, LongTermItem, SessionInfo } from '../types'

export default function MemoryPanel() {
  const { message, modal } = App.useApp()
  const [sessions, setSessions] = useState<SessionInfo[]>([])
  const [longTerm, setLongTerm] = useState<LongTermItem[]>([])
  const [loading, setLoading] = useState(true)
  const [keyword, setKeyword] = useState('')
  const [searchResults, setSearchResults] = useState<ChatMessage[]>([])
  const [rememberOpen, setRememberOpen] = useState(false)
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try {
      const [sessionList, memories] = await Promise.all([api.listSessions(), api.listLongTerm()])
      setSessions(sessionList)
      setLongTerm(memories)
    } catch (err) { message.error((err as Error).message) }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const showMessages = async (session: SessionInfo) => {
    try {
      const messages = await api.getMessages(session.id)
      modal.info({ title: session.title || `会话 ${session.id.slice(0, 8)}`, width: 720, content: <div style={{ maxHeight: 480, overflow: 'auto' }}>{messages.map((m, i) => <div key={i} style={{ marginBottom: 12 }}><Tag color={m.role === 'user' ? 'blue' : 'purple'}>{m.role}</Tag><span style={{ whiteSpace: 'pre-wrap' }}>{m.content}</span></div>)}</div> })
    } catch (err) { message.error((err as Error).message) }
  }

  const search = async () => {
    if (!keyword.trim()) return
    try { setSearchResults(await api.searchHistory(keyword.trim())) }
    catch (err) { message.error((err as Error).message) }
  }

  const remember = async () => {
    const values = await form.validateFields()
    try {
      await api.remember(values)
      message.success('长期记忆已保存')
      setRememberOpen(false)
      form.resetFields()
      await load()
    } catch (err) { message.error((err as Error).message) }
  }

  const cleanup = async () => {
    try {
      const result = await api.cleanupMemory()
      message.success(result.message || '过期记忆已清理')
      await load()
    } catch (err) { message.error((err as Error).message) }
  }

  const sessionColumns: ColumnsType<SessionInfo> = [
    { title: '会话', dataIndex: 'title', render: (v, row) => <Button type="link" onClick={() => showMessages(row)}>{v || row.id.slice(0, 8)}</Button> },
    { title: '创建时间', dataIndex: 'created_at', width: 180, render: (v) => new Date(v * 1000).toLocaleString() },
    { title: '更新时间', dataIndex: 'updated_at', width: 180, render: (v) => new Date(v * 1000).toLocaleString() },
    { title: '操作', width: 90, render: (_, row) => <Popconfirm title="删除该会话？" onConfirm={async () => { await api.deleteSession(row.id); await load() }}><Button danger type="text" icon={<DeleteOutlined />} /></Popconfirm> },
  ]
  const memoryColumns: ColumnsType<LongTermItem> = [
    { title: 'Key', dataIndex: 'key', width: 180, render: (v) => <Typography.Text strong>{v}</Typography.Text> },
    { title: '内容', dataIndex: 'value', render: (v) => <Typography.Paragraph ellipsis={{ rows: 2, expandable: true }} style={{ marginBottom: 0 }}>{v}</Typography.Paragraph> },
    { title: '主题', dataIndex: 'topic', width: 130, render: (v) => v ? <Tag color="blue">{v}</Tag> : <Tag>默认</Tag> },
    { title: '重要度', dataIndex: 'importance', width: 110, render: (v) => <Tag color={v >= 4 ? 'red' : v >= 3 ? 'orange' : 'default'}>{v}/5</Tag> },
  ]

  return (
    <div>
      <div className="page-header"><div><h2 className="page-title">记忆管理</h2><p className="page-description">管理多轮会话、长期语义记忆与过期数据清理，保障上下文连续性。</p></div><div className="page-actions"><Button icon={<ClearOutlined />} onClick={cleanup}>清理过期</Button><Button type="primary" icon={<PlusOutlined />} onClick={() => setRememberOpen(true)}>写入记忆</Button></div></div>
      <Row gutter={[18, 18]} style={{ marginBottom: 18 }}>
        <Col xs={24} md={8}><Card className="panel-card stat-card"><div className="stat-label">会话数量</div><div className="stat-value">{sessions.length}</div><div className="stat-extra">多轮上下文</div></Card></Col>
        <Col xs={24} md={8}><Card className="panel-card stat-card"><div className="stat-label">长期记忆</div><div className="stat-value">{longTerm.length}</div><div className="stat-extra">跨会话知识</div></Card></Col>
        <Col xs={24} md={8}><Card className="panel-card stat-card"><div className="stat-label">检索命中</div><div className="stat-value">{searchResults.length}</div><div className="stat-extra">历史搜索</div></Card></Col>
      </Row>
      <Card className="panel-card">
        <Tabs items={[
          { key: 'sessions', label: '会话记忆', children: <Table rowKey="id" loading={loading} columns={sessionColumns} dataSource={sessions} pagination={{ pageSize: 8 }} scroll={{ x: 700 }} /> },
          { key: 'longterm', label: '长期记忆', children: <Table rowKey="id" loading={loading} columns={memoryColumns} dataSource={longTerm} pagination={{ pageSize: 8 }} scroll={{ x: 820 }} /> },
          { key: 'search', label: '历史检索', children: <div><Space.Compact style={{ width: '100%', maxWidth: 720 }}><Input size="large" prefix={<SearchOutlined />} placeholder="搜索历史对话关键词" value={keyword} onChange={(e) => setKeyword(e.target.value)} onPressEnter={search} /><Button size="large" type="primary" onClick={search}>搜索</Button></Space.Compact><List style={{ marginTop: 16 }} dataSource={searchResults} locale={{ emptyText: <Empty description="输入关键词检索历史消息" /> }} renderItem={(item) => <List.Item className="soft-section"><div><Tag color={item.role === 'user' ? 'blue' : 'purple'}>{item.role}</Tag><Typography.Text>{item.content}</Typography.Text></div></List.Item>} /></div> },
        ]} />
      </Card>
      <Modal title="写入长期记忆" open={rememberOpen} onOk={remember} onCancel={() => setRememberOpen(false)} okText="保存">
        <Form form={form} layout="vertical" initialValues={{ importance: 3, topic: 'general' }}>
          <Form.Item name="key" label="Key" rules={[{ required: true, message: '请输入 key' }]}><Input placeholder="例如 user_preference" /></Form.Item>
          <Form.Item name="value" label="记忆内容" rules={[{ required: true, message: '请输入内容' }]}><Input.TextArea rows={4} /></Form.Item>
          <Form.Item name="topic" label="主题"><Select options={['general', 'preference', 'project', 'fact'].map((v) => ({ value: v, label: v }))} /></Form.Item>
          <Form.Item name="importance" label="重要度"><Slider min={1} max={5} marks={{ 1: '1', 3: '3', 5: '5' }} /></Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

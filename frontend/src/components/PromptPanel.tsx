import { useEffect, useState } from 'react'
import { App, Button, Card, Col, Form, Input, List, Popconfirm, Row, Space, Tag, Typography } from 'antd'
import CodeOutlined from '@ant-design/icons/CodeOutlined'
import DeleteOutlined from '@ant-design/icons/DeleteOutlined'
import EditOutlined from '@ant-design/icons/EditOutlined'
import PlusOutlined from '@ant-design/icons/PlusOutlined'
import ReloadOutlined from '@ant-design/icons/ReloadOutlined'
import { api } from '../api/client'
import type { PromptTemplate } from '../types'

export default function PromptPanel() {
  const { message } = App.useApp()
  const [prompts, setPrompts] = useState<PromptTemplate[]>([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState<PromptTemplate | null>(null)
  const [creating, setCreating] = useState(false)
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try { setPrompts(await api.listPrompts()) }
    catch (err) { message.error((err as Error).message) }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const openEdit = (item: PromptTemplate) => {
    setEditing(item)
    form.setFieldsValue(item)
  }
  const save = async () => {
    const values = await form.validateFields()
    try {
      if (creating) await api.createPrompt(values)
      else if (editing) await api.updatePrompt(editing.name, { description: values.description, template: values.template })
      message.success('提示词模板已保存')
      setEditing(null)
      setCreating(false)
      form.resetFields()
      await load()
    } catch (err) { message.error((err as Error).message) }
  }
  const remove = async (item: PromptTemplate) => {
    try {
      await api.deletePrompt(item.name)
      message.success(item.is_builtin ? '已恢复内置模板' : '模板已删除')
      await load()
    } catch (err) { message.error((err as Error).message) }
  }

  return (
    <div>
      <div className="page-header"><div><h2 className="page-title">提示工程</h2><p className="page-description">统一管理 RAG、Agent、评估等链路的提示词模板，支持覆盖内置模板与自定义扩展。</p></div><div className="page-actions"><Button icon={<ReloadOutlined />} onClick={load}>刷新</Button><Button type="primary" icon={<PlusOutlined />} onClick={() => { setCreating(true); setEditing({ name: '', description: '', template: '' }); form.resetFields() }}>新建模板</Button></div></div>
      <Row gutter={[18, 18]}>
        <Col xs={24} lg={9}>
          <Card className="panel-card" title="模板清单" loading={loading}>
            <List dataSource={prompts} renderItem={(item) => <List.Item actions={[<Button key="edit" type="text" icon={<EditOutlined />} onClick={() => openEdit(item)} />, <Popconfirm key="delete" title={item.is_builtin ? '重置该内置模板？' : '删除该模板？'} onConfirm={() => remove(item)}><Button type="text" danger icon={<DeleteOutlined />} /></Popconfirm>]}><List.Item.Meta avatar={<CodeOutlined style={{ fontSize: 22, color: '#4f63ff' }} />} title={<Space>{item.name}{item.is_builtin ? <Tag color="blue">内置</Tag> : <Tag color="green">自定义</Tag>}{item.is_overridden && <Tag color="orange">已覆盖</Tag>}</Space>} description={item.description} /></List.Item>} />
          </Card>
        </Col>
        <Col xs={24} lg={15}>
          <Card className="panel-card" title={editing ? `编辑：${editing.name || '新模板'}` : '模板预览'}>
            {editing ? (
              <Form form={form} layout="vertical">
                <Form.Item name="name" label="模板名称" rules={[{ required: true, whitespace: true, message: '请输入非空名称' }]}><Input disabled={!creating && !!editing?.name} placeholder="例如 rag_answer" /></Form.Item>
                <Form.Item name="description" label="用途说明" rules={[{ required: true, whitespace: true, message: '请输入非空说明' }]}><Input placeholder="描述该模板在哪个链路使用" /></Form.Item>
                <Form.Item name="template" label="模板内容" rules={[{ required: true, whitespace: true, message: '请输入非空模板' }]}><Input.TextArea rows={14} className="mono" placeholder="支持 {context}、{question} 等变量，按后端模板约定填写" /></Form.Item>
                <Space><Button type="primary" onClick={save}>保存模板</Button><Button onClick={() => { setEditing(null); setCreating(false) }}>取消</Button></Space>
              </Form>
            ) : (
              <div>
                <Typography.Paragraph type="secondary">从左侧选择一个模板查看内容，或新建自定义模板。</Typography.Paragraph>
                {prompts.slice(0, 3).map((item) => <div key={item.name} className="soft-section" style={{ marginBottom: 12, cursor: 'pointer' }} onClick={() => openEdit(item)}><Space><Typography.Text strong>{item.name}</Typography.Text>{item.is_builtin ? <Tag color="blue">内置</Tag> : <Tag color="green">自定义</Tag>}</Space><pre className="code-view" style={{ marginTop: 10, maxHeight: 180 }}>{item.template.slice(0, 700)}</pre></div>)}
              </div>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}

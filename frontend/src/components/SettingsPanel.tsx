import { useEffect, useState } from 'react'
import { App, Button, Card, Col, Form, Input, InputNumber, Row, Space, Switch, Tabs, Tag, Typography } from 'antd'
import CheckCircleOutlined from '@ant-design/icons/CheckCircleOutlined'
import CloudServerOutlined from '@ant-design/icons/CloudServerOutlined'
import KeyOutlined from '@ant-design/icons/KeyOutlined'
import ReloadOutlined from '@ant-design/icons/ReloadOutlined'
import SafetyCertificateOutlined from '@ant-design/icons/SafetyCertificateOutlined'
import { api } from '../api/client'
import type { SettingsSnapshot } from '../types'


export default function SettingsPanel() {
  const { message } = App.useApp()
  const [snapshot, setSnapshot] = useState<SettingsSnapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [testing, setTesting] = useState('')
  const [llmForms] = Form.useForm()
  const [embeddingForm] = Form.useForm()
  const [rerankerForm] = Form.useForm()

  const fillForms = (data: SettingsSnapshot) => {
    const values: Record<string, unknown> = {}
    data.llm.forEach((item) => {
      values[`${item.provider}.model`] = item.model
      values[`${item.provider}.base_url`] = item.base_url
      values[`${item.provider}.api_key`] = ''
    })
    llmForms.setFieldsValue(values)
    embeddingForm.setFieldsValue({ ...data.embedding, api_key: '' })
    rerankerForm.setFieldsValue({ ...data.reranker, api_key: '' })
  }
  const load = async () => {
    setLoading(true)
    try {
      const data = await api.getSettings()
      setSnapshot(data)
      fillForms(data)
    } catch (err) { message.error((err as Error).message) }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const saveDefault = async (provider: string) => {
    try {
      const data = await api.updateDefaultProvider(provider)
      setSnapshot(data)
      message.success('默认模型已切换')
    } catch (err) { message.error((err as Error).message) }
  }
  const saveLLM = async (provider: string) => {
    const values = llmForms.getFieldsValue()
    const current = snapshot?.llm.find((item) => item.provider === provider)
    const modelValue = values[`${provider}.model`]
    const baseUrlValue = values[`${provider}.base_url`]
    try {
      const data = await api.updateLLMConfig(provider, {
        api_key: values[`${provider}.api_key`] || undefined,
        base_url: baseUrlValue && baseUrlValue !== current?.base_url ? baseUrlValue : undefined,
        model: modelValue && modelValue !== current?.model ? modelValue : undefined,
      })
      setSnapshot(data)
      message.success('LLM 配置已保存；密钥不回显')
    } catch (err) { message.error((err as Error).message) }
  }
  const saveEmbedding = async () => {
    const values = await embeddingForm.validateFields()
    try {
      const data = await api.updateEmbeddingConfig({ ...values, api_key: values.api_key || undefined })
      setSnapshot(data)
      fillForms(data)
      message.success('嵌入配置已保存；如更换模型，建议重建索引')
    } catch (err) { message.error((err as Error).message) }
  }
  const saveReranker = async () => {
    const values = await rerankerForm.validateFields()
    try {
      const data = await api.updateRerankerConfig({ ...values, api_key: values.api_key || undefined })
      setSnapshot(data)
      fillForms(data)
      message.success('重排序配置已保存')
    } catch (err) { message.error((err as Error).message) }
  }
  const test = async (section: 'llm' | 'reranker', provider?: string) => {
    const key = `${section}:${provider || 'default'}`
    setTesting(key)
    try {
      const result = await api.testConnection({ section, provider })
      result.ok ? message.success(result.message) : message.warning(result.message)
    } catch (err) { message.error((err as Error).message) }
    finally { setTesting('') }
  }

  const llmTab = (
    <Form form={llmForms} layout="vertical">
      <Row gutter={[18, 18]}>
        {snapshot?.llm.map((item) => (
          <Col xs={24} xl={12} key={item.provider}>
            <Card className="subtle-card" title={<Space><CloudServerOutlined />{item.provider}</Space>} extra={<Space>{item.has_key ? <Tag color="success">已配置密钥</Tag> : <Tag color="warning">未配置密钥</Tag>}{snapshot.default_provider === item.provider && <Tag color="blue">默认</Tag>}</Space>}>
              <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>{item.description}</Typography.Paragraph><Form.Item name={`${item.provider}.model`} label="模型"><Input placeholder="模型名称" /></Form.Item>
              <Form.Item name={`${item.provider}.base_url`} label="Base URL"><Input placeholder="https://api.example.com/v1" /></Form.Item>
              <Form.Item name={`${item.provider}.api_key`} label={`API Key（当前：${item.api_key_masked || '未配置'}）`}><Input.Password placeholder="输入新密钥；留空则不修改" autoComplete="new-password" /></Form.Item>
              <Space wrap><Button type="primary" onClick={() => saveLLM(item.provider)}>保存</Button><Button loading={testing === `llm:${item.provider}`} onClick={() => test('llm', item.provider)}>测试连接</Button><Button onClick={() => saveDefault(item.provider)} disabled={snapshot.default_provider === item.provider || !item.available}>设为默认</Button></Space>
            </Card>
          </Col>
        ))}
      </Row>
    </Form>
  )

  return (
    <div>
      <div className="page-header"><div><h2 className="page-title">系统设置</h2><p className="page-description">统一管理模型提供方、嵌入、重排序与密钥。页面只展示掩码，真实密钥不会回显。</p></div><div className="page-actions"><Button icon={<ReloadOutlined />} loading={loading} onClick={load}>重新加载</Button></div></div>
      <Row gutter={[18, 18]} style={{ marginBottom: 18 }}>
        <Col xs={24} md={8}><Card className="panel-card stat-card"><div className="stat-label">默认提供方</div><div className="stat-value" style={{ fontSize: 20 }}>{snapshot?.default_provider || '-'}</div><div className="stat-extra">运行时模型路由</div></Card></Col>
        <Col xs={24} md={8}><Card className="panel-card stat-card"><div className="stat-label">可用 LLM</div><div className="stat-value">{snapshot?.llm.filter((i) => i.available).length ?? 0}</div><div className="stat-extra">已配置密钥的提供方</div></Card></Col>
        <Col xs={24} md={8}><Card className="panel-card stat-card"><div className="stat-label">Reranker</div><div className="stat-value" style={{ fontSize: 20 }}>{snapshot?.reranker.enabled ? 'Enabled' : 'Disabled'}</div><div className="stat-extra">两阶段检索</div></Card></Col>
      </Row>
      <Card className="panel-card" loading={loading}>
        <Tabs items={[
          { key: 'llm', label: 'LLM 提供方', children: llmTab },
          { key: 'embedding', label: '嵌入模型', children: <Form form={embeddingForm} layout="vertical" style={{ maxWidth: 760 }}><Row gutter={16}><Col xs={24} md={12}><Form.Item name="provider" label="Provider"><Input /></Form.Item></Col><Col xs={24} md={12}><Form.Item name="model" label="模型"><Input /></Form.Item></Col><Col xs={24} md={12}><Form.Item name="base_url" label="Base URL"><Input /></Form.Item></Col><Col xs={24} md={12}><Form.Item name="dimension" label="向量维度"><InputNumber style={{ width: '100%' }} min={1} /></Form.Item></Col><Col span={24}><Form.Item name="api_key" label={`API Key（当前：${snapshot?.embedding.api_key_masked || '未配置'}）`}><Input.Password placeholder="输入新密钥；留空则不修改" autoComplete="new-password" /></Form.Item></Col></Row><Button type="primary" onClick={saveEmbedding}>保存嵌入配置</Button></Form> },
          { key: 'reranker', label: '重排序', children: <Form form={rerankerForm} layout="vertical" style={{ maxWidth: 760 }}><Form.Item name="enabled" label="启用两阶段重排序" valuePropName="checked"><Switch /></Form.Item><Row gutter={16}><Col xs={24} md={12}><Form.Item name="model" label="模型"><Input /></Form.Item></Col><Col xs={24} md={12}><Form.Item name="base_url" label="Base URL"><Input /></Form.Item></Col><Col xs={24} md={12}><Form.Item name="top_n" label="Top N"><InputNumber style={{ width: '100%' }} min={1} /></Form.Item></Col><Col xs={24} md={12}><Form.Item name="candidate_k" label="候选数"><InputNumber style={{ width: '100%' }} min={1} /></Form.Item></Col><Col span={24}><Form.Item name="api_key" label={`API Key（当前：${snapshot?.reranker.api_key_masked || '未配置'}）`}><Input.Password placeholder="输入新密钥；留空则不修改" autoComplete="new-password" /></Form.Item></Col></Row><Space><Button type="primary" onClick={saveReranker}>保存重排序配置</Button><Button loading={testing === 'reranker:default'} onClick={() => test('reranker')}>测试连接</Button></Space></Form> },
          { key: 'security', label: '安全说明', children: <div className="two-col"><div className="soft-section"><Space><KeyOutlined style={{ color: '#4f63ff' }} /><Typography.Text strong>密钥脱敏</Typography.Text></Space><Typography.Paragraph type="secondary">接口只返回掩码；留空或掩码不会覆盖现有密钥。生产蓝图建议进一步迁移到 Secret Manager/KMS。</Typography.Paragraph></div><div className="soft-section"><Space><SafetyCertificateOutlined style={{ color: '#16a34a' }} /><Typography.Text strong>生产提醒</Typography.Text></Space><Typography.Paragraph type="secondary">当前单机版本尚未实现认证、多租户与审计；请在生产化路线中优先完成 P0 安全底座。</Typography.Paragraph></div><div className="soft-section"><Space><CheckCircleOutlined style={{ color: '#16a34a' }} /><Typography.Text strong>热更新</Typography.Text></Space><Typography.Paragraph type="secondary">配置保存后运行时生效，无需重启服务；嵌入模型更换后仍建议规划索引重建。</Typography.Paragraph></div></div> },
        ]} />
      </Card>
    </div>
  )
}

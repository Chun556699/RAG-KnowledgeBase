import { useState } from 'react'
import { App, Button, Card, Col, Form, Input, Progress, Row, Space, Tag, Typography } from 'antd'
import ExperimentOutlined from '@ant-design/icons/ExperimentOutlined'
import PlayCircleOutlined from '@ant-design/icons/PlayCircleOutlined'
import { api } from '../api/client'
import type { EvaluationResponse } from '../types'

export default function EvaluationPanel() {
  const { message } = App.useApp()
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<EvaluationResponse | null>(null)
  const [form] = Form.useForm()

  const evaluate = async () => {
    const values = await form.validateFields()
    setLoading(true)
    setResult(null)
    try { setResult(await api.evaluate(values)) }
    catch (err) { message.error((err as Error).message) }
    finally { setLoading(false) }
  }

  const scoreColor = (score: number) => score >= 0.8 ? '#16a34a' : score >= 0.55 ? '#d97706' : '#dc2626'
  const sample = {
    question: '什么是检索增强生成？',
    answer: '检索增强生成（RAG）是先检索相关知识，再把证据注入大模型上下文生成答案的技术。',
    context: 'RAG 将外部知识检索与生成模型结合，使回答可以引用企业知识库内容。',
  }

  return (
    <div>
      <div className="page-header"><div><h2 className="page-title">质量评估</h2><p className="page-description">使用 RAGAS 风格指标评估回答忠实度与相关性，为模型、Prompt 和检索策略回归提供依据。</p></div></div>
      <Row gutter={[18, 18]}>
        <Col xs={24} xl={13}>
          <Card className="panel-card" title={<Space><ExperimentOutlined />评估输入</Space>}>
            <Form form={form} layout="vertical" initialValues={sample}>
              <Form.Item name="question" label="用户问题" rules={[{ required: true, message: '请输入问题' }]}><Input size="large" /></Form.Item>
              <Form.Item name="answer" label="模型回答" rules={[{ required: true, message: '请输入回答' }]}><Input.TextArea rows={5} /></Form.Item>
              <Form.Item name="context" label="检索上下文（可选）"><Input.TextArea rows={6} placeholder="粘贴用于生成回答的证据上下文；为空时评估会更依赖问题/回答本身" /></Form.Item>
              <Button type="primary" icon={<PlayCircleOutlined />} size="large" loading={loading} onClick={evaluate}>运行评估</Button>
            </Form>
          </Card>
        </Col>
        <Col xs={24} xl={11}>
          <Card className="panel-card" title="评估结果">
            {!result ? <div style={{ minHeight: 330, display: 'grid', placeItems: 'center' }}><Typography.Text type="secondary">运行评估后显示指标与解释</Typography.Text></div> : (
              <Row gutter={[18, 18]}>
                <Col span={12} style={{ textAlign: 'center' }}><Progress type="dashboard" percent={Math.round(result.faithfulness * 100)} strokeColor={scoreColor(result.faithfulness)} /><Typography.Title level={5}>Faithfulness</Typography.Title><Typography.Text type="secondary">回答是否被证据支持</Typography.Text></Col>
                <Col span={12} style={{ textAlign: 'center' }}><Progress type="dashboard" percent={Math.round(result.answer_relevancy * 100)} strokeColor={scoreColor(result.answer_relevancy)} /><Typography.Title level={5}>Relevancy</Typography.Title><Typography.Text type="secondary">回答是否真正回应问题</Typography.Text></Col>
                <Col span={24}><div className="soft-section"><Space wrap><Tag color="blue">质量门禁建议</Tag><Typography.Text type="secondary">生产环境建议将核心黄金集指标纳入 CI，出现明显回归时阻断发布。</Typography.Text></Space></div></Col>
              </Row>
            )}
          </Card>
          <Card className="panel-card" title="指标解读" style={{ marginTop: 18 }}>
            <div className="soft-section"><Typography.Text strong>Faithfulness</Typography.Text><div className="muted">衡量回答中的声明能否从检索上下文中得到支持，越高越不容易幻觉。</div></div>
            <div className="soft-section" style={{ marginTop: 10 }}><Typography.Text strong>Answer Relevancy</Typography.Text><div className="muted">衡量回答是否聚焦用户问题，而不是泛泛而谈或偏离主题。</div></div>
          </Card>
        </Col>
      </Row>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { App, Button, Card, Col, Collapse, Input, Row, Space, Spin, Steps, Tag, Typography } from 'antd'
import ApiOutlined from '@ant-design/icons/ApiOutlined'
import CheckCircleOutlined from '@ant-design/icons/CheckCircleOutlined'
import PlayCircleOutlined from '@ant-design/icons/PlayCircleOutlined'
import ToolOutlined from '@ant-design/icons/ToolOutlined'
import { api } from '../api/client'
import type { AgentResponse, SelectedModel } from '../types'

const examples = ['帮我规划一次知识库质量评估', '检索知识库并总结向量检索要点', '计算 128 * 46 并说明结果']

export default function AgentPanel({ model }: { model: SelectedModel | null }) {
  const { message } = App.useApp()
  const [query, setQuery] = useState('')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<AgentResponse | null>(null)
  const [tools, setTools] = useState<{ name: string; description: string }[]>([])

  useEffect(() => { api.listTools().then(setTools).catch(() => undefined) }, [])

  const run = async () => {
    if (!query.trim() || running) return
    setRunning(true)
    setResult(null)
    try { setResult(await api.runAgent(query.trim(), model?.provider, model?.model)) }
    catch (err) { message.error((err as Error).message) }
    finally { setRunning(false) }
  }

  return (
    <div>
      <div className="page-header"><div><h2 className="page-title">智能体工作台</h2><p className="page-description">ReAct 任务规划、工具调用、执行观察与自我反思，全过程透明可审计。</p></div></div>
      <Row gutter={[18, 18]}>
        <Col xs={24} xl={9}>
          <Card className="panel-card" title="任务输入">
            <Input.TextArea value={query} onChange={(e) => setQuery(e.target.value)} placeholder="描述一个需要拆解和执行的复杂任务…" autoSize={{ minRows: 5, maxRows: 10 }} />
            <Button type="primary" icon={<PlayCircleOutlined />} size="large" block style={{ marginTop: 14 }} loading={running} onClick={run}>运行智能体</Button>
            <div className="divider-soft" />
            <Typography.Text type="secondary">示例任务</Typography.Text>
            <Space direction="vertical" style={{ width: '100%', marginTop: 8 }}>{examples.map((item) => <Button key={item} block onClick={() => setQuery(item)}>{item}</Button>)}</Space>
          </Card>
          <Card className="panel-card" title="可用工具" style={{ marginTop: 18 }}>
            <Space direction="vertical" style={{ width: '100%' }}>{tools.map((tool) => <div key={tool.name} className="soft-section"><Space><ToolOutlined style={{ color: '#4f63ff' }} /><Typography.Text strong>{tool.name}</Typography.Text></Space><div className="muted" style={{ marginTop: 4 }}>{tool.description}</div></div>)}</Space>
          </Card>
        </Col>
        <Col xs={24} xl={15}>
          <Card className="panel-card" title="执行轨迹">
            {running && <div style={{ minHeight: 260, display: 'grid', placeItems: 'center' }}><Spin size="large" tip="智能体规划与执行中…" /></div>}
            {!running && !result && <div style={{ minHeight: 260, display: 'grid', placeItems: 'center' }}><Typography.Text type="secondary">输入任务后，这里会展示规划、工具调用和反思过程</Typography.Text></div>}
            {result && (
              <div>
                <Steps direction="vertical" current={result.steps.length} items={result.steps.map((step) => ({
                  title: `步骤 ${step.step}：${step.description}`,
                  description: <div><Space wrap><Tag color="blue">{step.tool || 'reasoning'}</Tag></Space><Typography.Paragraph type="secondary" style={{ margin: '8px 0 0' }}>{step.thought}</Typography.Paragraph><div className="soft-section mono" style={{ whiteSpace: 'pre-wrap' }}>{step.output}</div></div>,
                  icon: <CheckCircleOutlined />,
                }))} />
                <Collapse style={{ marginTop: 18 }} items={[
                  { key: 'plan', label: `初始计划（${result.plan.length} 步）`, children: result.plan.map((item) => <div key={item.step} className="soft-section" style={{ marginBottom: 8 }}><Tag>{item.step}</Tag>{item.description}<div className="muted">{item.thought}</div></div>) },
                  { key: 'reflection', label: '自我反思', children: <Typography.Paragraph>{result.reflection || '无'}</Typography.Paragraph> },
                ]} />
                <Card className="subtle-card" style={{ marginTop: 18 }} title={<Space><ApiOutlined />最终答案</Space>}><Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>{result.answer}</Typography.Paragraph><Tag color="green">迭代 {result.iterations} 次</Tag></Card>
              </div>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}

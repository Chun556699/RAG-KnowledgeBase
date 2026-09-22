/**
 * 智能体（Agent）面板。
 *
 * 可视化展示 Agent 的"规划 → 执行 → 反思"闭环：
 *  - 输入复杂查询后，Agent 先将其分解为多个带工具标注的子任务（规划）；
 *  - 逐步执行子任务并调用工具（计算器 / 日期 / 知识库检索等）；
 *  - 汇总得出最终答案，并进行一次自我反思评估。
 * 左侧列出可用工具，右侧以时间线形式呈现完整执行轨迹。
 */
import { useEffect, useState } from 'react'
import { App, Button, Card, Col, Empty, Input, Row, Space, Spin, Tag } from 'antd'
import {
  ApartmentOutlined,
  CheckCircleOutlined,
  PlayCircleOutlined,
  SearchOutlined,
  ToolOutlined,
} from '@ant-design/icons'
import { api, ApiError } from '../api/client'
import type { AgentResponse, SelectedModel } from '../types'

interface Props {
  model: SelectedModel | null
}

export default function AgentPanel({ model }: Props) {
  const { message } = App.useApp()
  const [query, setQuery] = useState('')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<AgentResponse | null>(null)
  const [tools, setTools] = useState<{ name: string; description: string }[]>([])

  // 拉取可用工具列表用于展示
  useEffect(() => {
    api.listTools().then(setTools).catch(() => {
      /* 忽略工具列表加载失败 */
    })
  }, [])

  /** 运行 Agent */
  const run = async () => {
    const q = query.trim()
    if (!q || running) return
    setRunning(true)
    setResult(null)
    try {
      setResult(await api.runAgent(q, model?.provider, model?.model))
    } catch (e) {
      message.error((e as ApiError).message)
    } finally {
      setRunning(false)
    }
  }

  /** 示例问题，便于快速体验 */
  const examples = [
    '帮我计算 (128 + 56) * 3 等于多少',
    '现在几点了？顺便告诉我今天的日期',
    '从知识库里查找关于向量检索的内容并总结',
  ]

  return (
    <div>
      <h2 className="panel-title">智能体</h2>
      <p className="panel-desc">
        Agent 会自动将复杂问题拆解为子任务，按需调用工具执行，并在完成后进行自我反思。
      </p>

      <Row gutter={16}>
        {/* 左：输入 + 可用工具 */}
        <Col xs={24} lg={12}>
          <Card title="提出任务" style={{ marginBottom: 16 }}>
            <Input.TextArea
              style={{ width: '100%' }}
              rows={4}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="描述一个需要多步骤或工具协作的任务…"
              disabled={running}
            />
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              onClick={run}
              disabled={running || !query.trim()}
              loading={running}
              style={{ marginTop: 10 }}
            >
              {running ? '执行中' : '运行 Agent'}
            </Button>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 12 }}>示例：</div>
            <Space wrap style={{ marginTop: 6 }}>
              {examples.map((ex, i) => (
                <Tag key={i} style={{ cursor: 'pointer' }} onClick={() => setQuery(ex)}>
                  {ex}
                </Tag>
              ))}
            </Space>
          </Card>

          <Card
            title={
              <Space>
                <ToolOutlined /> 可用工具（{tools.length}）
              </Space>
            }
          >
            {tools.map((t) => (
              <div key={t.name} style={{ marginBottom: 8 }}>
                <Tag color="purple">{t.name}</Tag>{' '}
                <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{t.description}</span>
              </div>
            ))}
          </Card>
        </Col>

        {/* 右：执行轨迹 */}
        <Col xs={24} lg={12}>
          {running && (
            <Card style={{ marginBottom: 16 }}>
              <Space>
                <Spin size="small" /> Agent 正在规划与执行…
              </Space>
            </Card>
          )}

          {result && (
            <>
              {/* 规划 */}
              <Card
                title={
                  <Space>
                    <ApartmentOutlined /> 任务规划（{result.plan.length} 步 · ReAct）
                  </Space>
                }
                style={{ marginBottom: 16 }}
              >
                {result.plan.map((p) => (
                  <div key={p.step} className="trace-step">
                    <div className="step-head">
                      步骤 {p.step}：{p.description}
                    </div>
                    {p.thought && <div className="step-thought">推理：{p.thought}</div>}
                    {p.tool && <Tag color="purple">工具：{p.tool}</Tag>}
                  </div>
                ))}
              </Card>

              {/* 执行过程 */}
              <Card
                title={
                  <Space>
                    <PlayCircleOutlined /> 执行轨迹（推理 → 行动 → 观察）
                  </Space>
                }
                style={{ marginBottom: 16 }}
              >
                {result.steps.map((s) => (
                  <div key={s.step} className="trace-step">
                    <div className="step-head">
                      步骤 {s.step}：{s.description}
                      {s.tool && <Tag color="purple" style={{ marginLeft: 6 }}>{s.tool}</Tag>}
                    </div>
                    {s.thought && <div className="step-thought">推理：{s.thought}</div>}
                    <div className="step-output">
                      <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>观察：</span>{' '}
                      {s.output}
                    </div>
                  </div>
                ))}
              </Card>

              {/* 最终答案 */}
              <Card
                title={
                  <Space>
                    <CheckCircleOutlined /> 最终答案
                  </Space>
                }
                style={{ marginBottom: 16 }}
              >
                <div style={{ whiteSpace: 'pre-wrap' }}>{result.answer}</div>
              </Card>

              {/* 反思 */}
              <Card
                title={
                  <Space>
                    <SearchOutlined /> 自我反思（迭代 {result.iterations} 轮）
                  </Space>
                }
              >
                <div style={{ color: 'var(--text-secondary)' }}>{result.reflection}</div>
              </Card>
            </>
          )}

          {!running && !result && (
            <Card>
              <Empty description="在左侧输入任务并运行，这里将展示完整的执行轨迹" />
            </Card>
          )}
        </Col>
      </Row>
    </div>
  )
}

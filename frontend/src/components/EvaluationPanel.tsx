/**
 * 质量评估面板（RAGAS）。
 *
 * 输入「问题 + 回答 + 检索上下文」，调用后端 /api/evaluation 获得
 * 忠实度（faithfulness）与答案相关性（answer_relevancy）两个指标，
 * 以进度环可视化展示，用于评估 RAG 回答质量、辅助调试与回归。
 */
import { useState } from 'react'
import { App, Button, Card, Col, Input, Progress, Row, Space } from 'antd'
import { ExperimentOutlined } from '@ant-design/icons'
import { api } from '../api/client'
import { ArrowFillButton } from '@/components/block/arrow-fill-button'
import type { EvaluationResponse } from '../types'

/** 演示用预设样例 */
const SAMPLE = {
  question: '什么是 RAG？',
  answer:
    'RAG（检索增强生成）是一种结合信息检索与文本生成的技术，先从知识库检索相关片段，再交给大模型生成回答，从而减少幻觉。',
  context:
    '检索增强生成（RAG）是一种结合信息检索与文本生成的技术。它先从知识库检索相关文档片段，再把检索结果作为上下文交给大语言模型生成回答，从而显著减少幻觉、提高准确性。',
}

/** 分数 → 进度环颜色 */
const scoreColor = (pct: number) => (pct >= 80 ? '#059669' : pct >= 50 ? '#d97706' : '#dc2626')

export default function EvaluationPanel() {
  const { message } = App.useApp()
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [context, setContext] = useState('')
  const [result, setResult] = useState<EvaluationResponse | null>(null)
  const [loading, setLoading] = useState(false)

  const runEval = async () => {
    if (!question.trim() || !answer.trim()) {
      message.warning('请填写「问题」和「回答」后再评估')
      return
    }
    setLoading(true)
    setResult(null)
    try {
      const r = await api.evaluate({
        question: question.trim(),
        answer: answer.trim(),
        context: context.trim() || undefined,
      })
      setResult(r)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '评估失败')
    } finally {
      setLoading(false)
    }
  }

  const fillSample = () => {
    setQuestion(SAMPLE.question)
    setAnswer(SAMPLE.answer)
    setContext(SAMPLE.context)
    setResult(null)
  }

  return (
    <div>
      <h2 className="panel-title">质量评估</h2>
      <p className="panel-desc">
        基于 RAGAS 思想对一次问答结果打分：忠实度（是否编造）与答案相关性（是否切题），
        分数由 LLM 自动评估，用于量化 RAG 质量。
      </p>

      <Row gutter={16}>
        <Col xs={24} lg={12}>
          <Card title="评估输入" style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 4 }}>
                  用户问题
                </div>
                <Input.TextArea
                  rows={3}
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="例如：什么是 RAG？"
                />
              </div>
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 4 }}>
                  系统回答
                </div>
                <Input.TextArea
                  rows={3}
                  value={answer}
                  onChange={(e) => setAnswer(e.target.value)}
                  placeholder="待评估的回答内容"
                />
              </div>
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 4 }}>
                  检索上下文（可选，用于忠实度评估）
                </div>
                <Input.TextArea
                  rows={3}
                  value={context}
                  onChange={(e) => setContext(e.target.value)}
                  placeholder="本次问答所依据的检索片段"
                />
              </div>
              <Space>
                <ArrowFillButton
                  as="button"
                  onClick={runEval}
                  disabled={loading}
                  bgColor="var(--primary)"
                  textColor="#ffffff"
                  fillBgColor="var(--surface)"
                  fillTextColor="var(--primary)"
                  hoverFillBgColor="var(--accent)"
                  hoverFillTextColor="#ffffff"
                  style={{ opacity: loading ? 0.6 : 1 }}
                >
                  {loading ? '评估中…' : '开始评估'}
                </ArrowFillButton>
                <Button onClick={fillSample} disabled={loading}>
                  填入示例
                </Button>
              </Space>
            </div>
          </Card>
        </Col>

        <Col xs={24} lg={12}>
          {result && (
            <Card
              title={
                <Space>
                  <ExperimentOutlined /> 评估结果
                </Space>
              }
            >
              <Space size={48} style={{ width: '100%', justifyContent: 'center', padding: '12px 0' }}>
                <Progress
                  type="dashboard"
                  percent={Math.round(result.faithfulness * 100)}
                  strokeColor={scoreColor(Math.round(result.faithfulness * 100))}
                  format={(p) => `${p}%`}
                />
                <Progress
                  type="dashboard"
                  percent={Math.round(result.answer_relevancy * 100)}
                  strokeColor={scoreColor(Math.round(result.answer_relevancy * 100))}
                  format={(p) => `${p}%`}
                />
              </Space>
              <Row>
                <Col span={12} style={{ textAlign: 'center' }}>
                  <div style={{ fontWeight: 600 }}>忠实度</div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                    faithfulness：回答是否忠于检索上下文、无编造
                  </div>
                </Col>
                <Col span={12} style={{ textAlign: 'center' }}>
                  <div style={{ fontWeight: 600 }}>答案相关性</div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                    answer_relevancy：回答是否切题完整
                  </div>
                </Col>
              </Row>
            </Card>
          )}
        </Col>
      </Row>
    </div>
  )
}

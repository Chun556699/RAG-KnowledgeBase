/**
 * 质量评估面板（RAGAS）。
 *
 * 输入「问题 + 回答 + 检索上下文」，调用后端 /api/evaluation 获得
 * 忠实度（faithfulness）与答案相关性（answer_relevancy）两个指标，
 * 以进度条可视化展示，用于评估 RAG 回答质量、辅助调试与回归。
 */
import { useState } from 'react'
import { api } from '../api/client'
import type { EvaluationResponse } from '../types'
import Icon from './Icon'

/** 演示用预设样例 */
const SAMPLE = {
  question: '什么是 RAG？',
  answer: 'RAG（检索增强生成）是一种结合信息检索与文本生成的技术，先从知识库检索相关片段，再交给大模型生成回答，从而减少幻觉。',
  context: '检索增强生成（RAG）是一种结合信息检索与文本生成的技术。它先从知识库检索相关文档片段，再把检索结果作为上下文交给大语言模型生成回答，从而显著减少幻觉、提高准确性。',
}

function ScoreBar({ label, score }: { label: string; score: number }) {
  const pct = Math.round(score * 100)
  const color = pct >= 80 ? '#16a34a' : pct >= 50 ? '#d97706' : '#dc2626'
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
        <span style={{ fontWeight: 600 }}>{label}</span>
        <span style={{ color, fontWeight: 700 }}>{pct}%</span>
      </div>
      <div
        style={{
          height: 10,
          background: '#e5e7eb',
          borderRadius: 5,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: '100%',
            background: color,
            borderRadius: 5,
            transition: 'width 0.4s ease',
          }}
        />
      </div>
      <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>
        {label === '忠实度 faithfulness'
          ? '回答是否忠于检索上下文、无编造（幻觉）'
          : '回答是否直接、完整地回应问题'}
      </div>
    </div>
  )
}

export default function EvaluationPanel() {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [context, setContext] = useState('')
  const [result, setResult] = useState<EvaluationResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const runEval = async () => {
    if (!question.trim() || !answer.trim()) {
      setError('请填写「问题」和「回答」后再评估')
      return
    }
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const r = await api.evaluate({
        question: question.trim(),
        answer: answer.trim(),
        context: context.trim() || undefined,
      })
      setResult(r)
    } catch (e) {
      setError(e instanceof Error ? e.message : '评估失败')
    } finally {
      setLoading(false)
    }
  }

  const fillSample = () => {
    setQuestion(SAMPLE.question)
    setAnswer(SAMPLE.answer)
    setContext(SAMPLE.context)
    setResult(null)
    setError('')
  }

  return (
    <div className="eval-container">
      <h2 className="panel-title">质量评估</h2>
      <p className="panel-desc">
        基于 RAGAS 思想对一次问答结果打分：忠实度（是否编造）与答案相关性（是否切题），
        分数由 LLM 自动评估，用于量化 RAG 质量。
      </p>

      {error && (
        <div className="alert error">
          <Icon name="alert" size={16} /> {error}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
        <div>
          <label className="field-label">用户问题</label>
          <textarea
            className="textarea"
            rows={3}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="例如：什么是 RAG？"
          />
        </div>
        <div>
          <label className="field-label">系统回答</label>
          <textarea
            className="textarea"
            rows={3}
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            placeholder="待评估的回答内容"
          />
        </div>
      </div>

      <div style={{ marginBottom: 16 }}>
        <label className="field-label">检索上下文（可选，用于忠实度评估）</label>
        <textarea
          className="textarea"
          rows={3}
          value={context}
          onChange={(e) => setContext(e.target.value)}
          placeholder="本次问答所依据的检索片段"
        />
      </div>

      <div style={{ display: 'flex', gap: 12 }}>
        <button className="btn-primary" onClick={runEval} disabled={loading}>
          <Icon name="sparkle" size={16} /> {loading ? '评估中…' : '开始评估'}
        </button>
        <button className="btn-ghost" onClick={fillSample} disabled={loading}>
          填入示例
        </button>
      </div>

      {result && (
        <div style={{ marginTop: 24, padding: 20, border: '1px solid #e5e7eb', borderRadius: 10 }}>
          <h3 style={{ margin: '0 0 16px', fontSize: 16 }}>评估结果</h3>
          <ScoreBar label="忠实度 faithfulness" score={result.faithfulness} />
          <ScoreBar label="答案相关性 answer_relevancy" score={result.answer_relevancy} />
        </div>
      )}
    </div>
  )
}

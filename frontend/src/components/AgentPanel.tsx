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
import { api, ApiError } from '../api/client'
import type { AgentResponse, SelectedModel } from '../types'
import Icon from './Icon'

interface Props {
  model: SelectedModel | null
}

export default function AgentPanel({ model }: Props) {
  const [query, setQuery] = useState('')
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
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
    setError('')
    setResult(null)
    try {
      setResult(await api.runAgent(q, model?.provider, model?.model))
    } catch (e) {
      setError((e as ApiError).message)
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

      {error && (
        <div className="alert error">
          <Icon name="alert" size={16} /> {error}
        </div>
      )}

      <div className="grid-2">
        {/* 左：输入 + 可用工具 */}
        <div>
          <div className="card">
            <strong>提出任务</strong>
            <textarea
              style={{ width: '100%', marginTop: 10, minHeight: 90, resize: 'vertical' }}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="描述一个需要多步骤或工具协作的任务…"
              disabled={running}
            />
            <div className="toolbar" style={{ marginTop: 10 }}>
              <button className="btn-primary" onClick={run} disabled={running || !query.trim()}>
                <Icon name="activity" size={15} /> {running ? '执行中…' : '运行 Agent'}
              </button>
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>示例：</div>
            {examples.map((ex, i) => (
              <div
                key={i}
                className="tag"
                style={{ cursor: 'pointer', display: 'block', marginTop: 6 }}
                onClick={() => setQuery(ex)}
              >
                {ex}
              </div>
            ))}
          </div>

          <div className="card">
            <div className="card-title">
              <Icon name="tool" size={16} /> 可用工具（{tools.length}）
            </div>
            <div className="list" style={{ marginTop: 10 }}>
              {tools.map((t) => (
                <div key={t.name}>
                  <span className="tag tool">{t.name}</span>{' '}
                  <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>{t.description}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* 右：执行轨迹 */}
        <div>
          {running && (
            <div className="card">
              <span className="spinner" /> Agent 正在规划与执行…
            </div>
          )}

          {result && (
            <>
              {/* 规划 */}
              <div className="card">
                <div className="card-title">
                  <Icon name="list" size={16} /> 任务规划（{result.plan.length} 步 · ReAct）
                </div>
                <div style={{ marginTop: 10 }}>
                  {result.plan.map((p) => (
                    <div key={p.step} className="trace-step">
                      <div className="step-head">
                        步骤 {p.step}：{p.description}
                      </div>
                      {p.thought && (
                        <div className="step-thought">
                          <Icon name="activity" size={13} /> 推理：{p.thought}
                        </div>
                      )}
                      {p.tool && <span className="tag tool">工具：{p.tool}</span>}
                    </div>
                  ))}
                </div>
              </div>

              {/* 执行过程 */}
              <div className="card">
                <div className="card-title">
                  <Icon name="activity" size={16} /> 执行轨迹（推理 → 行动 → 观察）
                </div>
                <div style={{ marginTop: 10 }}>
                  {result.steps.map((s) => (
                    <div key={s.step} className="trace-step">
                      <div className="step-head">
                        步骤 {s.step}：{s.description}
                        {s.tool && <span className="tag tool"> {s.tool}</span>}
                      </div>
                      {s.thought && (
                        <div className="step-thought">
                          <Icon name="activity" size={13} /> 推理：{s.thought}
                        </div>
                      )}
                      <div className="step-output">
                        <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>观察：</span>{' '}
                        {s.output}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* 最终答案 */}
              <div className="card">
                <div className="card-title">
                  <Icon name="check" size={16} /> 最终答案
                </div>
                <div style={{ marginTop: 10, whiteSpace: 'pre-wrap' }}>{result.answer}</div>
              </div>

              {/* 反思 */}
              <div className="card">
                <div className="card-title">
                  <Icon name="search" size={16} /> 自我反思（迭代 {result.iterations} 轮）
                </div>
                <div style={{ marginTop: 10, color: 'var(--text-muted)' }}>{result.reflection}</div>
              </div>
            </>
          )}

          {!running && !result && (
            <div className="empty">在左侧输入任务并运行，这里将展示完整的执行轨迹。</div>
          )}
        </div>
      </div>
    </div>
  )
}

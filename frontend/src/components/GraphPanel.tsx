/**
 * 知识图谱面板。
 *
 * 从知识库全量语料中，由后端调用 LLM 抽取「实体-关系-实体」三元组并聚合，
 * 前端用 cytoscape 力导向布局将其可视化：
 *  - 节点大小随权重（关联度）变化，越核心的实体越大；
 *  - 有向边标注关系文字；
 *  - 点击节点可查看其相邻关系；
 *  - 支持一键重建（重新抽取）。
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import type { Core, ElementDefinition } from 'cytoscape'
import CytoscapeComponent from 'react-cytoscapejs'
import { api, ApiError } from '../api/client'
import type { GraphData, SelectedModel } from '../types'
import Icon from './Icon'

interface Props {
  model: SelectedModel | null
}

export default function GraphPanel({ model }: Props) {
  const [graph, setGraph] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(false)
  const [building, setBuilding] = useState(false)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const cyRef = useRef<Core | null>(null)

  // 挂载后拉取已有图谱
  useEffect(() => {
    setLoading(true)
    api
      .getGraph()
      .then(setGraph)
      .catch((e) => setError((e as ApiError).message))
      .finally(() => setLoading(false))
  }, [])

  /** 触发重建（调用 LLM 抽取，耗时较长） */
  const rebuild = async () => {
    if (building) return
    setBuilding(true)
    setError('')
    setSelected(null)
    try {
      const data = await api.buildGraph({
        provider: model?.provider,
        model: model?.model,
      })
      setGraph(data)
    } catch (e) {
      setError((e as ApiError).message)
    } finally {
      setBuilding(false)
    }
  }

  // 将图谱数据转换为 cytoscape 元素
  const elements = useMemo<ElementDefinition[]>(() => {
    if (!graph) return []
    const nodes: ElementDefinition[] = graph.nodes.map((n) => ({
      data: { id: n.id, label: n.label, weight: n.weight },
    }))
    const edges: ElementDefinition[] = graph.edges.map((e, i) => ({
      data: {
        id: `e${i}`,
        source: e.source,
        target: e.target,
        relation: e.relation,
      },
    }))
    return [...nodes, ...edges]
  }, [graph])

  // 被选中节点的相邻关系（供右侧详情展示）
  const neighbors = useMemo(() => {
    if (!graph || !selected) return []
    return graph.edges
      .filter((e) => e.source === selected || e.target === selected)
      .map((e) => {
        const isOut = e.source === selected
        const otherId = isOut ? e.target : e.source
        const other = graph.nodes.find((n) => n.id === otherId)
        return {
          dir: isOut ? '→' : '←',
          relation: e.relation,
          label: other?.label ?? otherId,
        }
      })
  }, [graph, selected])

  const selectedLabel = useMemo(
    () => graph?.nodes.find((n) => n.id === selected)?.label ?? '',
    [graph, selected],
  )

  const hasData = !!graph && graph.nodes.length > 0

  return (
    <div>
      <h2 className="panel-title">知识图谱</h2>
      <p className="panel-desc">
        由大模型从知识库文档中抽取实体与关系，聚合为可视化图谱。点击节点查看其关联关系。
      </p>

      {error && (
        <div className="alert error">
          <Icon name="alert" size={16} /> {error}
        </div>
      )}

      <div className="toolbar" style={{ marginBottom: 12 }}>
        <button className="btn-primary" onClick={rebuild} disabled={building}>
          <Icon name="refresh" size={15} /> {building ? '构建中…' : '重新构建图谱'}
        </button>
        {graph?.built_at && (
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            上次构建：{new Date(graph.built_at * 1000).toLocaleString()}
          </span>
        )}
        {hasData && (
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            {graph!.nodes.length} 个实体 · {graph!.edges.length} 条关系
          </span>
        )}
      </div>

      {building && (
        <div className="card">
          <span className="spinner" /> 正在调用大模型抽取实体关系并构建图谱，请稍候…
        </div>
      )}

      {!building && !hasData && (
        <div className="empty">
          {loading
            ? '加载中…'
            : '暂无图谱数据。请先在「知识库」中上传文档，再点击上方「重新构建图谱」由大模型抽取实体关系。'}
        </div>
      )}

      {!building && hasData && (
        <div className="grid-2" style={{ gridTemplateColumns: '1fr 300px' }}>
          {/* 左：图谱画布 */}
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <CytoscapeComponent
              elements={elements}
              style={{ width: '100%', height: 560 }}
              minZoom={0.2}
              maxZoom={2.5}
              layout={{ name: 'cose', animate: false, padding: 30 } as never}
              stylesheet={
                [
                  {
                    selector: 'node',
                    style: {
                      label: 'data(label)',
                      'background-color': '#6366f1',
                      color: '#e5e7eb',
                      'font-size': 10,
                      'text-valign': 'bottom',
                      'text-halign': 'center',
                      'text-margin-y': 4,
                      width: 'mapData(weight, 1, 10, 16, 52)',
                      height: 'mapData(weight, 1, 10, 16, 52)',
                    },
                  },
                  {
                    selector: 'node:selected',
                    style: {
                      'background-color': '#f59e0b',
                      'border-width': 2,
                      'border-color': '#fbbf24',
                    },
                  },
                  {
                    selector: 'edge',
                    style: {
                      label: 'data(relation)',
                      width: 1.5,
                      'line-color': '#4b5563',
                      'target-arrow-color': '#4b5563',
                      'target-arrow-shape': 'triangle',
                      'curve-style': 'bezier',
                      'font-size': 8,
                      color: '#9ca3af',
                      'text-rotation': 'autorotate',
                    },
                  },
                ] as never
              }
              cy={(cy: Core) => {
                cyRef.current = cy
                cy.removeAllListeners()
                cy.on('tap', 'node', (evt) => setSelected(evt.target.id()))
                cy.on('tap', (evt) => {
                  if (evt.target === cy) setSelected(null)
                })
              }}
            />
          </div>

          {/* 右：节点详情 */}
          <div>
            <div className="card">
              <div className="card-title">
                <Icon name="graph" size={16} /> 节点详情
              </div>
              {selected ? (
                <div style={{ marginTop: 10 }}>
                  <div style={{ fontWeight: 600, marginBottom: 8 }}>{selectedLabel}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8 }}>
                    关联 {neighbors.length} 条关系
                  </div>
                  <div className="list">
                    {neighbors.map((nb, i) => (
                      <div key={i} style={{ fontSize: 13, marginTop: 6 }}>
                        <span className="tag tool">{nb.relation}</span>{' '}
                        <span style={{ color: 'var(--text-muted)' }}>{nb.dir}</span>{' '}
                        {nb.label}
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div style={{ marginTop: 10, fontSize: 13, color: 'var(--text-muted)' }}>
                  点击左侧任意节点，查看它与其他实体的关联关系。
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

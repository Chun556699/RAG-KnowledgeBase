import { useEffect, useMemo, useRef, useState } from 'react'
import type { Core, ElementDefinition } from 'cytoscape'
import CytoscapeComponent from 'react-cytoscapejs'
import { Alert, Button, Card, Col, Empty, List, Row, Space, Spin, Tag, Typography } from 'antd'
import BranchesOutlined from '@ant-design/icons/BranchesOutlined'
import ReloadOutlined from '@ant-design/icons/ReloadOutlined'
import { api } from '../api/client'
import type { GraphData, SelectedModel } from '../types'

export default function GraphPanel({ model }: { model: SelectedModel | null }) {
  const [graph, setGraph] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(false)
  const [building, setBuilding] = useState(false)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const cyRef = useRef<Core | null>(null)

  useEffect(() => {
    setLoading(true)
    api.getGraph().then(setGraph).catch((e) => setError((e as Error).message)).finally(() => setLoading(false))
  }, [])

  const rebuild = async () => {
    setBuilding(true)
    setError('')
    try { setGraph(await api.buildGraph({ provider: model?.provider, model: model?.model })) }
    catch (e) { setError((e as Error).message) }
    finally { setBuilding(false) }
  }

  const elements = useMemo<ElementDefinition[]>(() => {
    if (!graph) return []
    return [
      ...graph.nodes.map((n) => ({ data: { id: n.id, label: n.label, weight: n.weight } })),
      ...graph.edges.map((e, i) => ({ data: { id: `e${i}`, source: e.source, target: e.target, relation: e.relation } })),
    ]
  }, [graph])

  const neighbors = useMemo(() => {
    if (!graph || !selected) return []
    return graph.edges.filter((e) => e.source === selected || e.target === selected).map((e) => {
      const isOut = e.source === selected
      const otherId = isOut ? e.target : e.source
      return { dir: isOut ? '→' : '←', relation: e.relation, label: graph.nodes.find((n) => n.id === otherId)?.label ?? otherId }
    })
  }, [graph, selected])
  const selectedLabel = graph?.nodes.find((n) => n.id === selected)?.label ?? ''
  const hasData = !!graph && graph.nodes.length > 0

  return (
    <div>
      <div className="page-header"><div><h2 className="page-title">知识图谱</h2><p className="page-description">实体关系抽取与可视化探索，用于多跳关系和 GraphRAG 辅助检索。</p></div><div className="page-actions"><Button type="primary" icon={<ReloadOutlined />} loading={building} onClick={rebuild}>重新构建图谱</Button></div></div>
      {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} closable onClose={() => setError('')} />}
      <Row gutter={[18, 18]} style={{ marginBottom: 18 }}>
        <Col xs={24} md={8}><Card className="panel-card stat-card"><div className="stat-label">实体节点</div><div className="stat-value">{graph?.nodes.length ?? 0}</div></Card></Col>
        <Col xs={24} md={8}><Card className="panel-card stat-card"><div className="stat-label">关系边</div><div className="stat-value">{graph?.edges.length ?? 0}</div></Card></Col>
        <Col xs={24} md={8}><Card className="panel-card stat-card"><div className="stat-label">上次构建</div><div className="stat-value" style={{ fontSize: 16 }}>{graph?.built_at ? new Date(graph.built_at * 1000).toLocaleString() : '未构建'}</div></Card></Col>
      </Row>
      <Row gutter={[18, 18]}>
        <Col xs={24} xl={17}>
          <Card className="panel-card" bodyStyle={{ padding: 0 }}>
            {building ? <div style={{ height: 560, display: 'grid', placeItems: 'center' }}><Spin size="large" tip="正在调用大模型抽取实体关系…" /></div> : hasData ? (
              <div className="graph-canvas"><CytoscapeComponent elements={elements} style={{ width: '100%', height: 560 }} minZoom={0.2} maxZoom={2.5} layout={{ name: 'cose', animate: false, padding: 30 } as never} stylesheet={[
                { selector: 'node', style: { label: 'data(label)', 'background-color': '#4f63ff', color: '#172033', 'font-size': 10, 'text-valign': 'bottom', 'text-halign': 'center', 'text-margin-y': 5, width: 'mapData(weight, 1, 10, 18, 54)', height: 'mapData(weight, 1, 10, 18, 54)' } },
                { selector: 'node:selected', style: { 'background-color': '#f59e0b', 'border-width': 3, 'border-color': '#fbbf24' } },
                { selector: 'edge', style: { label: 'data(relation)', width: 1.6, 'line-color': '#a7b0c3', 'target-arrow-color': '#a7b0c3', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', 'font-size': 8, color: '#68758d', 'text-rotation': 'autorotate' } },
              ] as never} cy={(cy: Core) => { cyRef.current = cy; cy.removeAllListeners(); cy.on('tap', 'node', (evt) => setSelected(evt.target.id())); cy.on('tap', (evt) => { if (evt.target === cy) setSelected(null) }) }} /></div>
            ) : <div style={{ height: 420, display: 'grid', placeItems: 'center' }}><Empty description={loading ? '加载中…' : '暂无图谱数据，请先上传文档并构建'} /></div>}
          </Card>
        </Col>
        <Col xs={24} xl={7}>
          <Card className="panel-card" title={<Space><BranchesOutlined />节点详情</Space>}>
            {selected ? <div><Typography.Title level={4} style={{ marginTop: 0 }}>{selectedLabel}</Typography.Title><Tag color="blue">关联 {neighbors.length} 条关系</Tag><List style={{ marginTop: 14 }} dataSource={neighbors} renderItem={(item) => <List.Item><Space><Tag color="purple">{item.relation}</Tag><span className="muted">{item.dir}</span><span>{item.label}</span></Space></List.Item>} /></div> : <Empty description="点击左侧节点查看关联关系" />}
          </Card>
        </Col>
      </Row>
    </div>
  )
}

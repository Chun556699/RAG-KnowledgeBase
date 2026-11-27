import { useEffect, useState } from 'react'
import { App, Button, Card, Col, Input, Popconfirm, Row, Space, Statistic, Table, Tag, Typography, Upload } from 'antd'
import CloudUploadOutlined from '@ant-design/icons/CloudUploadOutlined'
import DeleteOutlined from '@ant-design/icons/DeleteOutlined'
import FileTextOutlined from '@ant-design/icons/FileTextOutlined'
import ReloadOutlined from '@ant-design/icons/ReloadOutlined'
import SearchOutlined from '@ant-design/icons/SearchOutlined'
import type { ColumnsType } from 'antd/es/table'
import { api } from '../api/client'
import type { DocumentInfo, RetrievedChunk } from '../types'

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export default function DocumentsPanel() {
  const { message } = App.useApp()
  const [docs, setDocs] = useState<DocumentInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [query, setQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [results, setResults] = useState<RetrievedChunk[]>([])

  const load = async () => {
    setLoading(true)
    try { setDocs(await api.listDocuments()) }
    catch (err) { message.error((err as Error).message) }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const upload = async (file: File) => {
    setUploading(true)
    try {
      const doc = await api.uploadDocument(file)
      message.success(`${doc.filename} 已索引 ${doc.chunk_count} 个片段`)
      await load()
    } catch (err) { message.error((err as Error).message) }
    finally { setUploading(false) }
    return false
  }

  const remove = async (doc: DocumentInfo) => {
    try {
      await api.deleteDocument(doc.document_id)
      message.success(`已删除 ${doc.filename}`)
      await load()
    } catch (err) { message.error((err as Error).message) }
  }

  const search = async () => {
    if (!query.trim()) return
    setSearching(true)
    try { setResults((await api.search(query.trim(), 6)).chunks) }
    catch (err) { message.error((err as Error).message) }
    finally { setSearching(false) }
  }

  const columns: ColumnsType<DocumentInfo> = [
    { title: '文档', dataIndex: 'filename', render: (name: string) => <Space><FileTextOutlined style={{ color: '#4f63ff' }} /><Typography.Text strong>{name}</Typography.Text></Space> },
    { title: '片段数', dataIndex: 'chunk_count', width: 110, render: (v: number) => <Tag color="blue">{v} chunks</Tag> },
    { title: '大小', dataIndex: 'size_bytes', width: 110, render: formatSize },
    { title: '上传时间', dataIndex: 'created_at', width: 180, render: (v: number) => new Date(v * 1000).toLocaleString() },
    { title: '操作', width: 110, render: (_, doc) => <Popconfirm title="删除文档及其索引？" onConfirm={() => remove(doc)}><Button danger type="text" icon={<DeleteOutlined />} /></Popconfirm> },
  ]

  const totalChunks = docs.reduce((sum, doc) => sum + doc.chunk_count, 0)
  const totalBytes = docs.reduce((sum, doc) => sum + doc.size_bytes, 0)

  return (
    <div>
      <div className="page-header">
        <div><h2 className="page-title">知识库管理</h2><p className="page-description">上传、索引、检索测试与文档生命周期管理。当前版本支持 PDF / Word / TXT / Markdown。</p></div>
        <div className="page-actions"><Button icon={<ReloadOutlined />} onClick={load} loading={loading}>刷新</Button></div>
      </div>
      <Row gutter={[18, 18]} style={{ marginBottom: 18 }}>
        <Col xs={24} md={8}><Card className="panel-card stat-card"><Statistic title="文档总数" value={docs.length} suffix="份" /></Card></Col>
        <Col xs={24} md={8}><Card className="panel-card stat-card"><Statistic title="索引片段" value={totalChunks} suffix="个" /></Card></Col>
        <Col xs={24} md={8}><Card className="panel-card stat-card"><Statistic title="语料体积" value={formatSize(totalBytes)} /></Card></Col>
      </Row>
      <Row gutter={[18, 18]}>
        <Col xs={24} xl={10}>
          <Card className="panel-card" title="文档摄取">
            <Upload.Dragger className="file-drop" multiple showUploadList={false} accept=".txt,.md,.markdown,.pdf,.docx" beforeUpload={(file) => upload(file)} disabled={uploading}>
              <p><CloudUploadOutlined style={{ fontSize: 38, color: '#4f63ff' }} /></p>
              <Typography.Title level={4} style={{ marginTop: 0 }}>点击或拖拽上传文档</Typography.Title>
              <Typography.Text type="secondary">上传后将同步解析、分块并写入向量与稀疏索引</Typography.Text>
              {uploading && <div style={{ marginTop: 12 }}><Tag color="processing">正在解析索引…</Tag></div>}
            </Upload.Dragger>
            <div className="divider-soft" />
            <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>生产建议：大文件上传、OCR、病毒扫描和异步摄取已在 2.0 蓝图中规划。</Typography.Paragraph>
          </Card>
          <Card className="panel-card" title="语义检索测试" style={{ marginTop: 18 }}>
            <Space.Compact style={{ width: '100%' }}>
              <Input size="large" placeholder="输入关键词或自然语言问题" value={query} onChange={(e) => setQuery(e.target.value)} onPressEnter={search} />
              <Button size="large" type="primary" icon={<SearchOutlined />} loading={searching} onClick={search}>检索</Button>
            </Space.Compact>
            <div style={{ marginTop: 14, display: 'grid', gap: 10 }}>
              {results.map((item, index) => <div key={index} className="soft-section"><Space wrap><Tag color="blue">{item.filename}</Tag><Tag>{(item.score * 100).toFixed(0)}%</Tag></Space><Typography.Paragraph style={{ margin: '8px 0 0' }} type="secondary">{item.text.slice(0, 180)}{item.text.length > 180 ? '…' : ''}</Typography.Paragraph></div>)}
            </div>
          </Card>
        </Col>
        <Col xs={24} xl={14}>
          <Card className="panel-card" title="文档索引清单">
            <Table rowKey="document_id" loading={loading} columns={columns} dataSource={docs} pagination={{ pageSize: 8, showSizeChanger: false }} locale={{ emptyText: '暂无文档，请先上传' }} scroll={{ x: 720 }} />
          </Card>
        </Col>
      </Row>
    </div>
  )
}

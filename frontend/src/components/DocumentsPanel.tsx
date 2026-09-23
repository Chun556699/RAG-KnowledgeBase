/**
 * 知识库文档面板。
 *
 * 展示 RAG 的数据侧能力：
 *  - 拖拽/点击上传文档（PDF / Word / TXT / Markdown），后端自动解析、切分、向量化入库；
 *  - 文档表格展示分块数、大小、所属知识库等信息，支持删除（同步清理向量）；
 *  - 语义检索输入框：输入查询后返回向量相似度最高的文档片段，直观演示检索效果；
 *  - 多租户：可按知识库过滤列表、指定上传归属。
 */
import { useEffect, useState } from 'react'
import {
  App,
  Button,
  Card,
  Empty,
  Input,
  Popconfirm,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Upload,
} from 'antd'
import {
  DeleteOutlined,
  FileTextOutlined,
  InboxOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import { api, ApiError } from '../api/client'
import type { DocumentInfo, KnowledgeBase, RetrievedChunk } from '../types'

export default function DocumentsPanel() {
  const { message } = App.useApp()
  const [docs, setDocs] = useState<DocumentInfo[]>([])
  const [kbs, setKbs] = useState<KnowledgeBase[]>([])
  // 当前查看/上传的目标知识库；空串 = 全部（仅列表）
  const [kb, setKb] = useState('default')
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [query, setQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [results, setResults] = useState<RetrievedChunk[]>([])

  /** 拉取文档列表（随知识库过滤） */
  const refresh = async () => {
    setLoading(true)
    try {
      setDocs(await api.listDocuments(kb || undefined))
    } catch (e) {
      message.error((e as ApiError).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    api
      .listKbs()
      .then(setKbs)
      .catch(() => setKbs([]))
  }, [])

  useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kb])

  /** 上传单个文件 */
  const upload = async (file: File) => {
    setUploading(true)
    try {
      const doc = await api.uploadDocument(file, kb || 'default')
      message.success(`已上传《${doc.filename}》，切分为 ${doc.chunk_count} 个片段并完成向量化。`)
      await refresh()
    } catch (e) {
      message.error((e as ApiError).message)
    } finally {
      setUploading(false)
    }
  }

  /** 删除文档 */
  const remove = async (id: string) => {
    try {
      await api.deleteDocument(id)
      message.success('已删除')
      await refresh()
    } catch (e) {
      message.error((e as ApiError).message)
    }
  }

  /** 语义检索 */
  const search = async () => {
    const q = query.trim()
    if (!q) return
    setSearching(true)
    try {
      const res = await api.search(q, 5)
      setResults(res.chunks)
    } catch (e) {
      message.error((e as ApiError).message)
    } finally {
      setSearching(false)
    }
  }

  /** 格式化字节数为易读文本 */
  const fmtSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  }

  const kbName = (id?: string) => kbs.find((k) => k.kb_id === id)?.name ?? id

  const columns = [
    {
      title: '文档',
      dataIndex: 'filename',
      key: 'filename',
      render: (name: string) => (
        <Space>
          <FileTextOutlined style={{ color: 'var(--text-muted)' }} />
          <span style={{ fontWeight: 500 }}>{name}</span>
        </Space>
      ),
    },
    {
      title: '片段数',
      dataIndex: 'chunk_count',
      key: 'chunk_count',
      width: 90,
    },
    {
      title: '大小',
      dataIndex: 'size_bytes',
      key: 'size_bytes',
      width: 100,
      render: (v: number) => fmtSize(v),
    },
    {
      title: '知识库',
      dataIndex: 'kb_id',
      key: 'kb_id',
      width: 140,
      render: (id?: string) =>
        id && id !== 'default' ? <Tag color="blue">{kbName(id) ?? id}</Tag> : <Tag>默认库</Tag>,
    },
    {
      title: '入库时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (t: number) => new Date(t * 1000).toLocaleString(),
    },
    {
      title: '',
      key: 'actions',
      width: 90,
      render: (_: unknown, d: DocumentInfo) => (
        <Popconfirm
          title={`删除「${d.filename}」及其全部向量片段？`}
          okText="删除"
          cancelText="取消"
          okButtonProps={{ danger: true }}
          onConfirm={() => remove(d.document_id)}
        >
          <Button type="text" danger icon={<DeleteOutlined />}>
            删除
          </Button>
        </Popconfirm>
      ),
    },
  ]

  return (
    <div>
      <h2 className="panel-title">知识库</h2>
      <p className="panel-desc">
        上传文档后自动完成解析、分块与向量化入库，可用于对话检索或在下方进行语义检索测试。
      </p>

      {/* 上传区 */}
      <Upload.Dragger
        accept=".pdf,.docx,.txt,.md,.markdown"
        showUploadList={false}
        disabled={uploading}
        beforeUpload={(file) => {
          upload(file)
          return false // 阻止 antd 默认上传，交由自定义 api
        }}
        style={{ marginBottom: 16 }}
      >
        <div style={{ padding: '12px 0' }}>
          {uploading ? (
            <>
              <Spin /> <span style={{ marginLeft: 8 }}>正在上传并向量化…</span>
            </>
          ) : (
            <>
              <InboxOutlined style={{ fontSize: 36, color: 'var(--primary)' }} />
              <div style={{ marginTop: 8 }}>点击或拖拽文件到此处上传</div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                支持 PDF / Word(.docx) / TXT / Markdown · 上传至「{kbName(kb || 'default')}」
              </div>
            </>
          )}
        </div>
      </Upload.Dragger>

      {/* 语义检索 */}
      <Card
        title={
          <Space>
            <SearchOutlined /> 语义检索测试
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        <Space.Compact style={{ width: '100%' }}>
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onPressEnter={search}
            placeholder="输入查询语句，检索最相关的文档片段…"
          />
          <Button type="primary" onClick={search} disabled={searching || !query.trim()} loading={searching}>
            检索
          </Button>
        </Space.Compact>
        {results.length > 0 && (
          <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
            {results.map((r, i) => (
              <Card key={i} size="small">
                <Space style={{ marginBottom: 6 }}>
                  <Tag>{r.filename}</Tag>
                  <Tag color="success">相似度 {(r.score * 100).toFixed(1)}%</Tag>
                </Space>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{r.text}</div>
              </Card>
            ))}
          </div>
        )}
      </Card>

      {/* 文档列表 */}
      <Card
        title={`已入库文档（${docs.length}）`}
        extra={
          <Space>
            <Select
              size="small"
              style={{ minWidth: 160 }}
              value={kb}
              options={[
                { value: 'default', label: '默认库' },
                ...kbs
                  .filter((k) => k.kb_id !== 'default')
                  .map((k) => ({ value: k.kb_id, label: k.name })),
              ]}
              onChange={setKb}
            />
            <Button icon={<ReloadOutlined />} onClick={refresh} loading={loading} size="small">
              刷新
            </Button>
          </Space>
        }
      >
        <Table
          rowKey="document_id"
          dataSource={docs}
          columns={columns}
          loading={loading}
          pagination={docs.length > 10 ? { pageSize: 10 } : false}
          locale={{ emptyText: <Empty description="暂无文档，请先上传" /> }}
          size="middle"
        />
      </Card>
    </div>
  )
}

/**
 * 知识库文档面板。
 *
 * 展示 RAG 的数据侧能力：
 *  - 拖拽/点击上传文档（PDF / Word / TXT / Markdown），后端自动解析、切分、向量化入库；
 *  - 文档列表展示分块数、大小等索引信息，并支持删除（同步清理向量）；
 *  - 语义检索输入框：输入查询后返回向量相似度最高的文档片段，直观演示检索效果。
 */
import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api/client'
import type { DocumentInfo, RetrievedChunk } from '../types'
import Icon from './Icon'

export default function DocumentsPanel() {
  const [docs, setDocs] = useState<DocumentInfo[]>([])
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [query, setQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [results, setResults] = useState<RetrievedChunk[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  /** 拉取文档列表 */
  const refresh = async () => {
    setLoading(true)
    try {
      setDocs(await api.listDocuments())
    } catch (e) {
      setError((e as ApiError).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  /** 上传单个文件 */
  const upload = async (file: File) => {
    setUploading(true)
    setError('')
    setNotice('')
    try {
      const doc = await api.uploadDocument(file)
      setNotice(`已上传《${doc.filename}》，切分为 ${doc.chunk_count} 个片段并完成向量化。`)
      await refresh()
    } catch (e) {
      setError((e as ApiError).message)
    } finally {
      setUploading(false)
    }
  }

  /** 处理文件选择 */
  const handleFiles = (files: FileList | null) => {
    if (files && files.length > 0) upload(files[0])
  }

  /** 拖拽释放 */
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    handleFiles(e.dataTransfer.files)
  }

  /** 删除文档 */
  const remove = async (id: string) => {
    try {
      await api.deleteDocument(id)
      await refresh()
    } catch (e) {
      setError((e as ApiError).message)
    }
  }

  /** 语义检索 */
  const search = async () => {
    const q = query.trim()
    if (!q) return
    setSearching(true)
    setError('')
    try {
      const res = await api.search(q, 5)
      setResults(res.chunks)
    } catch (e) {
      setError((e as ApiError).message)
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

  return (
    <div>
      <h2 className="panel-title">知识库</h2>
      <p className="panel-desc">
        上传文档后自动完成解析、分块与向量化入库，可用于对话检索或在下方进行语义检索测试。
      </p>

      {error && (
        <div className="alert error">
          <Icon name="alert" size={16} /> {error}
        </div>
      )}
      {notice && (
        <div className="alert success">
          <Icon name="check" size={16} /> {notice}
        </div>
      )}

      {/* 上传区 */}
      <div
        className={`dropzone ${dragging ? 'drag' : ''}`}
        onClick={() => fileInputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
      >
        {uploading ? (
          <div className="dz-inner">
            <span className="spinner" /> 正在上传并向量化…
          </div>
        ) : (
          <div className="dz-inner">
            <Icon name="upload" size={28} strokeWidth={1.6} />
            <div>点击或拖拽文件到此处上传</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              支持 PDF / Word(.docx) / TXT / Markdown
            </div>
          </div>
        )}
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx,.txt,.md,.markdown"
          style={{ display: 'none' }}
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      {/* 语义检索 */}
      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-title">
          <Icon name="search" size={16} /> 语义检索测试
        </div>
        <div className="toolbar" style={{ marginTop: 10 }}>
          <input
            style={{ flex: 1 }}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && search()}
            placeholder="输入查询语句，检索最相关的文档片段…"
          />
          <button className="btn-primary" onClick={search} disabled={searching || !query.trim()}>
            {searching ? '检索中…' : '检索'}
          </button>
        </div>
        {results.length > 0 && (
          <div className="list" style={{ marginTop: 12 }}>
            {results.map((r, i) => (
              <div key={i} className="card" style={{ margin: 0 }}>
                <div style={{ marginBottom: 6 }}>
                  <span className="tag">{r.filename}</span>{' '}
                  <span className="tag score">相似度 {(r.score * 100).toFixed(1)}%</span>
                </div>
                <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>{r.text}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 文档列表 */}
      <div className="toolbar">
        <strong>已入库文档（{docs.length}）</strong>
        <button className="btn-ghost" onClick={refresh} disabled={loading}>
          <Icon name="refresh" size={15} /> {loading ? '刷新中…' : '刷新'}
        </button>
      </div>
      {docs.length === 0 ? (
        <div className="empty">暂无文档，请先上传。</div>
      ) : (
        <div className="doc-list">
          {docs.map((d) => (
            <div key={d.document_id} className="doc-item">
              <div>
                <div className="doc-name">
                  <Icon name="file" size={16} /> {d.filename}
                </div>
                <div className="meta">
                  {d.chunk_count} 个片段 · {fmtSize(d.size_bytes)} ·{' '}
                  {new Date(d.created_at * 1000).toLocaleString()}
                </div>
              </div>
              <button className="btn-danger" onClick={() => remove(d.document_id)}>
                <Icon name="trash" size={15} /> 删除
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

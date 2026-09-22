/**
 * 嵌入集成面板（企业化）。
 *
 * 让管理员把知识库问答能力嵌入任意产品：
 *  - 知识库（租户）管理：创建、查看规模；
 *  - API 密钥管理：创建（明文仅此一次展示）/ 吊销 / 脱敏列表；
 *  - 嵌入代码生成器：选择密钥 + 知识库 + 外观，生成一行 <script> 集成代码，
 *    可一键复制或打开演示页预览。
 */
import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  ColorPicker,
  Empty,
  Input,
  Row,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import {
  BookOutlined,
  CodeOutlined,
  CopyOutlined,
  KeyOutlined,
  LinkOutlined,
  PlusOutlined,
} from '@ant-design/icons'
import { api } from '../api/client'
import type { ApiKeyInfo, KnowledgeBase } from '../types'

/** 脱敏密钥的占位（用于生成代码片段，真实密钥仅在创建时出现一次） */
const KEY_PLACEHOLDER = 'ak_live_…'

export default function EmbedPanel() {
  const { message } = App.useApp()
  const [kbs, setKbs] = useState<KnowledgeBase[]>([])
  const [keys, setKeys] = useState<ApiKeyInfo[]>([])

  // 新建知识库表单
  const [kbName, setKbName] = useState('')
  const [kbDesc, setKbDesc] = useState('')
  // 新建密钥表单
  const [keyName, setKeyName] = useState('')
  const [keyKb, setKeyKb] = useState('')
  // 刚创建的密钥明文（仅此一次可见）
  const [freshKey, setFreshKey] = useState('')

  // 代码片段定制项
  const [snipKb, setSnipKb] = useState('')
  const [snipTitle, setSnipTitle] = useState('智能助手')
  const [snipColor, setSnipColor] = useState('#4f46e5')
  const [snipPos, setSnipPos] = useState<'right' | 'left'>('right')

  const load = async () => {
    try {
      const [kbList, keyList] = await Promise.all([api.listKbs(), api.listKeys()])
      setKbs(kbList)
      setKeys(keyList)
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  useEffect(() => {
    load()
  }, [])

  /** 生成嵌入代码片段 */
  const snippet = useMemo(() => {
    const origin = window.location.origin
    const attrs = [
      `src="${origin}/embed/widget.js"`,
      `data-key="${freshKey || KEY_PLACEHOLDER}"`,
      snipKb && `data-kb="${snipKb}"`,
      snipTitle !== '智能助手' && `data-title="${snipTitle}"`,
      snipColor !== '#4f46e5' && `data-color="${snipColor}"`,
      snipPos === 'left' && `data-position="left"`,
      'async',
    ].filter(Boolean)
    return `<script\n  ${attrs.join('\n  ')}\n></script>`
  }, [freshKey, snipKb, snipTitle, snipColor, snipPos])

  const demoUrl = useMemo(() => {
    return `/embed/demo${freshKey ? `?key=${encodeURIComponent(freshKey)}` : ''}`
  }, [freshKey])

  const copySnippet = async () => {
    try {
      await navigator.clipboard.writeText(snippet)
      message.success('嵌入代码已复制到剪贴板')
    } catch {
      message.error('复制失败，请手动选择复制')
    }
  }

  const createKb = async () => {
    if (!kbName.trim()) return
    try {
      await api.createKb({ name: kbName.trim(), description: kbDesc.trim() })
      setKbName('')
      setKbDesc('')
      message.success('知识库已创建')
      load()
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  const createKey = async () => {
    if (!keyName.trim()) return
    try {
      const res = await api.createKey({
        name: keyName.trim(),
        scopes: ['ask'],
        kb_id: keyKb || undefined,
      })
      setFreshKey(res.raw_key)
      setKeyName('')
      message.success('密钥已创建，请立即保存——明文只显示这一次')
      load()
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  const revokeKey = async (id: string) => {
    try {
      await api.revokeKey(id)
      message.success('密钥已吊销')
      load()
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  const keyColumns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, k: ApiKeyInfo) => (
        <Space>
          <span style={{ fontWeight: 500 }}>{name}</span>
          {k.revoked && <Tag color="warning">已吊销</Tag>}
        </Space>
      ),
    },
    {
      title: '前缀',
      dataIndex: 'key_prefix',
      key: 'key_prefix',
      render: (p: string) => <Typography.Text code>{p}</Typography.Text>,
    },
    {
      title: '范围',
      dataIndex: 'kb_id',
      key: 'kb_id',
      render: (id?: string) =>
        id ? <Tag color="blue">{kbs.find((k) => k.kb_id === id)?.name ?? id}</Tag> : <Tag>全部知识库</Tag>,
    },
    {
      title: '最近使用',
      dataIndex: 'last_used_at',
      key: 'last_used_at',
      render: (t?: number) => (t ? new Date(t * 1000).toLocaleString() : '—'),
    },
    {
      title: '',
      key: 'actions',
      width: 80,
      render: (_: unknown, k: ApiKeyInfo) =>
        !k.revoked && (
          <Button type="text" danger size="small" onClick={() => revokeKey(k.key_id)}>
            吊销
          </Button>
        ),
    },
  ]

  return (
    <div>
      <h2 className="panel-title">嵌入集成</h2>
      <p className="panel-desc">
        把知识库问答能力嵌入任意产品：创建知识库隔离数据 → 签发 API 密钥 → 一行 script 接入。
        公共问答接口走 <code>/api/v1</code>，密钥可绑定知识库实现租户隔离。
      </p>

      <Row gutter={16}>
        {/* ---------- 知识库管理 ---------- */}
        <Col xs={24} lg={12}>
          <Card
            title={
              <Space>
                <BookOutlined /> 知识库
              </Space>
            }
            style={{ marginBottom: 16 }}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {kbs.map((kb) => (
                <Card key={kb.kb_id} size="small">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <div style={{ fontWeight: 500 }}>{kb.name}</div>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                        {kb.kb_id} · {kb.document_count} 篇文档 · {kb.chunk_count} 个片段
                      </div>
                    </div>
                    {kb.kb_id === 'default' && <Tag>内置</Tag>}
                  </div>
                </Card>
              ))}
            </div>
            <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 8 }}>
              <Input
                value={kbName}
                onChange={(e) => setKbName(e.target.value)}
                placeholder="名称，如：客服知识库、产品手册"
              />
              <Input
                value={kbDesc}
                onChange={(e) => setKbDesc(e.target.value)}
                placeholder="描述（可选）：这个知识库存什么内容"
              />
              <Button type="primary" icon={<PlusOutlined />} onClick={createKb} disabled={!kbName.trim()}>
                创建知识库
              </Button>
            </div>
          </Card>
        </Col>

        {/* ---------- API 密钥管理 ---------- */}
        <Col xs={24} lg={12}>
          <Card
            title={
              <Space>
                <KeyOutlined /> API 密钥
              </Space>
            }
            style={{ marginBottom: 16 }}
          >
            <Table
              rowKey="key_id"
              dataSource={keys}
              columns={keyColumns}
              size="small"
              pagination={false}
              locale={{ emptyText: <Empty description="还没有密钥，先创建一个" /> }}
              style={{ marginBottom: 14 }}
            />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <Input
                value={keyName}
                onChange={(e) => setKeyName(e.target.value)}
                placeholder="密钥名称，如：官网挂件、App 生产环境"
              />
              <Select
                value={keyKb || undefined}
                placeholder="绑定知识库（可选，绑定后仅可查该库）"
                allowClear
                options={kbs.map((kb) => ({ value: kb.kb_id, label: `${kb.name}（${kb.kb_id}）` }))}
                onChange={(v) => setKeyKb(v ?? '')}
              />
              <Button type="primary" icon={<PlusOutlined />} onClick={createKey} disabled={!keyName.trim()}>
                签发密钥
              </Button>
            </div>
          </Card>
        </Col>
      </Row>

      {/* ---------- 新密钥明文（仅此一次） ---------- */}
      {freshKey && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="新密钥（只显示这一次，请立即保存）"
          description={
            <Typography.Text copyable code style={{ userSelect: 'all' }}>
              {freshKey}
            </Typography.Text>
          }
        />
      )}

      {/* ---------- 嵌入代码生成器 ---------- */}
      <Card
        title={
          <Space>
            <CodeOutlined /> 嵌入代码生成器
          </Space>
        }
      >
        <p className="panel-desc" style={{ marginTop: 4, marginBottom: 14 }}>
          把下面代码粘到目标网页的 <code>&lt;body&gt;</code> 任意位置即可。挂件为纯原生 JS +
          Shadow DOM，与宿主页面样式完全隔离、零依赖。
        </p>
        <Space wrap style={{ marginBottom: 14 }}>
          <span>
            知识库：
            <Select
              size="small"
              style={{ minWidth: 150 }}
              value={snipKb || undefined}
              placeholder="默认（随密钥）"
              allowClear
              options={kbs.map((kb) => ({ value: kb.kb_id, label: kb.name }))}
              onChange={(v) => setSnipKb(v ?? '')}
            />
          </span>
          <span>
            标题：
            <Input
              size="small"
              value={snipTitle}
              onChange={(e) => setSnipTitle(e.target.value)}
              style={{ width: 120 }}
            />
          </span>
          <span>
            主题色：
            <ColorPicker
              size="small"
              value={snipColor}
              onChange={(c) => setSnipColor(c.toHexString())}
            />
          </span>
          <span>
            位置：
            <Segmented
              size="small"
              value={snipPos}
              options={[
                { value: 'right', label: '右下角' },
                { value: 'left', label: '左下角' },
              ]}
              onChange={(v) => setSnipPos(v as 'right' | 'left')}
            />
          </span>
        </Space>
        <Typography.Paragraph>
          <pre className="code-block">{snippet}</pre>
        </Typography.Paragraph>
        <Space>
          <Button type="primary" icon={<CopyOutlined />} onClick={copySnippet}>
            复制代码
          </Button>
          <Button icon={<LinkOutlined />} href={demoUrl} target="_blank">
            打开演示页{freshKey ? '（已带密钥）' : ''}
          </Button>
          {!freshKey && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              提示：演示页支持 <code>?key=ak_live_xxx</code> 参数直接预览
            </Typography.Text>
          )}
        </Space>
      </Card>
    </div>
  )
}

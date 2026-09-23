/**
 * 提示工程管理面板。
 *
 * 提供提示词模板（Prompt Template）的完整增删改查（CRUD）能力：
 *  - 列出所有模板（内置基线 + 用户自定义），内置模板带标记；
 *  - 新建自定义模板；
 *  - 编辑模板内容（编辑内置模板即生成「覆盖」，可随时重置为默认）；
 *  - 删除自定义模板；对被覆盖的内置模板执行删除即「重置为默认」。
 * 模板中的 {变量} 占位符会在运行时由后端动态渲染注入上下文。
 */
import { useEffect, useState } from 'react'
import {
  App,
  Button,
  Card,
  Col,
  Empty,
  Input,
  List,
  Popconfirm,
  Row,
  Space,
  Tag,
} from 'antd'
import {
  CodeOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  UndoOutlined,
} from '@ant-design/icons'
import { api, ApiError } from '../api/client'
import type { PromptTemplate } from '../types'

/** 编辑器草稿：新建或编辑时的表单状态 */
interface Draft {
  name: string
  description: string
  template: string
  /** true 表示新建模式（name 可编辑），false 表示编辑既有模板 */
  isNew: boolean
}

export default function PromptPanel() {
  const { message } = App.useApp()
  const [prompts, setPrompts] = useState<PromptTemplate[]>([])
  const [active, setActive] = useState<string | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [busy, setBusy] = useState(false)

  /** 拉取模板列表，并尽量保持当前选中项 */
  const load = async (keepName?: string) => {
    try {
      const list = await api.listPrompts()
      setPrompts(list)
      const next = keepName && list.some((p) => p.name === keepName) ? keepName : list[0]?.name ?? null
      setActive(next)
    } catch (e) {
      message.error((e as ApiError).message)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const current = prompts.find((p) => p.name === active)

  /** 进入新建模式 */
  const startCreate = () => {
    setDraft({ name: '', description: '', template: '', isNew: true })
  }

  /** 进入编辑模式（基于当前选中模板） */
  const startEdit = () => {
    if (!current) return
    setDraft({
      name: current.name,
      description: current.description,
      template: current.template,
      isNew: false,
    })
  }

  /** 保存草稿（新建或更新） */
  const save = async () => {
    if (!draft || busy) return
    const name = draft.name.trim()
    if (!name || !draft.template.trim()) {
      message.warning('模板名与内容均不能为空')
      return
    }
    setBusy(true)
    try {
      if (draft.isNew) {
        await api.createPrompt({ name, description: draft.description, template: draft.template })
        message.success('模板已创建')
      } else {
        await api.updatePrompt(name, { description: draft.description, template: draft.template })
        message.success('模板已保存')
      }
      setDraft(null)
      await load(name)
    } catch (e) {
      message.error((e as ApiError).message)
    } finally {
      setBusy(false)
    }
  }

  /** 删除自定义模板 / 重置被覆盖的内置模板 */
  const remove = async (p: PromptTemplate) => {
    if (busy) return
    setBusy(true)
    try {
      await api.deletePrompt(p.name)
      message.success(p.is_builtin ? '已重置为默认' : '模板已删除')
      if (draft && draft.name === p.name) setDraft(null)
      await load(p.name)
    } catch (e) {
      message.error((e as ApiError).message)
    } finally {
      setBusy(false)
    }
  }

  /** 删除按钮是否可用：自定义模板可删；被覆盖的内置模板可重置 */
  const canDelete = (p: PromptTemplate) => !p.is_builtin || !!p.is_overridden

  return (
    <div>
      <h2 className="panel-title">提示工程</h2>
      <p className="panel-desc">
        模板化管理提示词，将提示与业务逻辑解耦。支持新增、编辑、删除；模板中的 {'{变量}'} 会在运行时动态注入。
      </p>

      <Row gutter={16}>
        {/* 模板列表 */}
        <Col xs={24} lg={12}>
          <Card
            title={`模板列表（${prompts.length}）`}
            extra={
              <Button type="primary" size="small" icon={<PlusOutlined />} onClick={startCreate} disabled={busy}>
                新建
              </Button>
            }
          >
            <List
              size="small"
              dataSource={prompts}
              renderItem={(p) => {
                const isReset = p.is_builtin && p.is_overridden
                return (
                  <List.Item
                    style={{
                      cursor: 'pointer',
                      background: active === p.name ? 'var(--primary-soft)' : undefined,
                      borderRadius: 6,
                      padding: '10px 12px',
                    }}
                    onClick={() => {
                      setActive(p.name)
                      setDraft(null)
                    }}
                    actions={
                      canDelete(p)
                        ? [
                            <Popconfirm
                              key="del"
                              title={isReset ? `将内置模板「${p.name}」重置为默认？` : `删除自定义模板「${p.name}」？`}
                              okText={isReset ? '重置' : '删除'}
                              cancelText="取消"
                              okButtonProps={{ danger: !isReset }}
                              onConfirm={(e) => {
                                e?.stopPropagation()
                                remove(p)
                              }}
                            >
                              <Button
                                type="text"
                                size="small"
                                danger={!isReset}
                                icon={isReset ? <UndoOutlined /> : <DeleteOutlined />}
                                title={isReset ? '重置为默认' : '删除'}
                                onClick={(e) => e.stopPropagation()}
                                disabled={busy}
                              />
                            </Popconfirm>,
                          ]
                        : undefined
                    }
                  >
                    <List.Item.Meta
                      title={
                        <Space size={6}>
                          <Tag color="purple">{p.name}</Tag>
                          {p.is_builtin ? (
                            <Tag>{p.is_overridden ? '内置·已覆盖' : '内置'}</Tag>
                          ) : (
                            <Tag color="blue">自定义</Tag>
                          )}
                        </Space>
                      }
                      description={p.description}
                    />
                  </List.Item>
                )
              }}
            />
          </Card>
        </Col>

        {/* 模板详情 / 编辑器 */}
        <Col xs={24} lg={12}>
          <Card
            title={
              <Space>
                <CodeOutlined /> {draft ? (draft.isNew ? '新建模板' : `编辑：${draft.name}`) : '模板原文'}
              </Space>
            }
            extra={
              !draft &&
              current && (
                <Button size="small" icon={<EditOutlined />} onClick={startEdit} disabled={busy}>
                  编辑
                </Button>
              )
            }
          >
            {draft ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {draft.isNew && (
                  <Input
                    placeholder="模板名（唯一标识，如 my_prompt）"
                    value={draft.name}
                    onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                    disabled={busy}
                  />
                )}
                <Input
                  placeholder="模板用途说明"
                  value={draft.description}
                  onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                  disabled={busy}
                />
                <Input.TextArea
                  style={{ minHeight: 200, fontFamily: 'monospace' }}
                  placeholder="模板内容，可用 {变量} 占位符"
                  value={draft.template}
                  onChange={(e) => setDraft({ ...draft, template: e.target.value })}
                  disabled={busy}
                />
                <Space>
                  <Button type="primary" onClick={save} loading={busy}>
                    保存
                  </Button>
                  <Button onClick={() => setDraft(null)} disabled={busy}>
                    取消
                  </Button>
                </Space>
              </div>
            ) : current ? (
              <>
                <div style={{ margin: '4px 0 10px', color: 'var(--text-muted)', fontSize: 13 }}>
                  {current.description}
                </div>
                <div className="code-block">{current.template}</div>
              </>
            ) : (
              <Empty description="点击左侧模板查看内容，或点击「新建」创建模板" />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}

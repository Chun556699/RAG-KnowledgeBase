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
import { api, ApiError } from '../api/client'
import type { PromptTemplate } from '../types'
import Icon from './Icon'

/** 编辑器草稿：新建或编辑时的表单状态 */
interface Draft {
  name: string
  description: string
  template: string
  /** true 表示新建模式（name 可编辑），false 表示编辑既有模板 */
  isNew: boolean
}

export default function PromptPanel() {
  const [prompts, setPrompts] = useState<PromptTemplate[]>([])
  const [active, setActive] = useState<string | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  /** 拉取模板列表，并尽量保持当前选中项 */
  const load = async (keepName?: string) => {
    try {
      const list = await api.listPrompts()
      setPrompts(list)
      const next = keepName && list.some((p) => p.name === keepName) ? keepName : list[0]?.name ?? null
      setActive(next)
    } catch (e) {
      setError((e as ApiError).message)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const current = prompts.find((p) => p.name === active)

  /** 短暂提示，便于反馈操作结果 */
  const flash = (msg: string) => {
    setNotice(msg)
    window.setTimeout(() => setNotice(''), 2500)
  }

  /** 进入新建模式 */
  const startCreate = () => {
    setError('')
    setDraft({ name: '', description: '', template: '', isNew: true })
  }

  /** 进入编辑模式（基于当前选中模板） */
  const startEdit = () => {
    if (!current) return
    setError('')
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
      setError('模板名与内容均不能为空')
      return
    }
    setBusy(true)
    setError('')
    try {
      if (draft.isNew) {
        await api.createPrompt({ name, description: draft.description, template: draft.template })
        flash('模板已创建')
      } else {
        await api.updatePrompt(name, { description: draft.description, template: draft.template })
        flash('模板已保存')
      }
      setDraft(null)
      await load(name)
    } catch (e) {
      setError((e as ApiError).message)
    } finally {
      setBusy(false)
    }
  }

  /** 删除自定义模板 / 重置被覆盖的内置模板 */
  const remove = async (p: PromptTemplate) => {
    if (busy) return
    const isReset = p.is_builtin && p.is_overridden
    const tip = isReset
      ? `确定将内置模板「${p.name}」重置为默认内容吗？`
      : `确定删除自定义模板「${p.name}」吗？`
    if (!window.confirm(tip)) return
    setBusy(true)
    setError('')
    try {
      await api.deletePrompt(p.name)
      flash(isReset ? '已重置为默认' : '模板已删除')
      if (draft && draft.name === p.name) setDraft(null)
      await load(p.name)
    } catch (e) {
      setError((e as ApiError).message)
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

      {error && (
        <div className="alert error">
          <Icon name="alert" size={16} /> {error}
        </div>
      )}
      {notice && (
        <div className="alert">
          <Icon name="check" size={16} /> {notice}
        </div>
      )}

      <div className="grid-2">
        {/* 模板列表 */}
        <div className="card">
          <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>
              <Icon name="list" size={16} /> 模板列表（{prompts.length}）
            </span>
            <button className="btn-primary" onClick={startCreate} disabled={busy}>
              <Icon name="plus" size={14} /> 新建
            </button>
          </div>
          <div className="list" style={{ marginTop: 10 }}>
            {prompts.map((p) => (
              <div
                key={p.name}
                className="doc-item"
                style={{
                  cursor: 'pointer',
                  borderColor: active === p.name ? 'var(--primary)' : undefined,
                }}
                onClick={() => {
                  setActive(p.name)
                  setDraft(null)
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div>
                    <span className="tag tool">{p.name}</span>{' '}
                    {p.is_builtin ? (
                      <span className="tag">{p.is_overridden ? '内置·已覆盖' : '内置'}</span>
                    ) : (
                      <span className="tag">自定义</span>
                    )}
                  </div>
                  <div className="meta">{p.description}</div>
                </div>
                {canDelete(p) && (
                  <button
                    className="btn-ghost"
                    title={p.is_builtin ? '重置为默认' : '删除'}
                    onClick={(e) => {
                      e.stopPropagation()
                      remove(p)
                    }}
                    disabled={busy}
                  >
                    <Icon name={p.is_builtin ? 'search' : 'trash'} size={15} />
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* 模板详情 / 编辑器 */}
        <div className="card">
          {draft ? (
            <>
              <div className="card-title">
                <Icon name="code" size={16} /> {draft.isNew ? '新建模板' : `编辑：${draft.name}`}
              </div>
              {draft.isNew && (
                <input
                  style={{ width: '100%', marginTop: 10 }}
                  placeholder="模板名（唯一标识，如 my_prompt）"
                  value={draft.name}
                  onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                  disabled={busy}
                />
              )}
              <input
                style={{ width: '100%', marginTop: 10 }}
                placeholder="模板用途说明"
                value={draft.description}
                onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                disabled={busy}
              />
              <textarea
                style={{ width: '100%', marginTop: 10, minHeight: 200, resize: 'vertical', fontFamily: 'monospace' }}
                placeholder="模板内容，可用 {变量} 占位符"
                value={draft.template}
                onChange={(e) => setDraft({ ...draft, template: e.target.value })}
                disabled={busy}
              />
              <div className="toolbar" style={{ marginTop: 10 }}>
                <button className="btn-primary" onClick={save} disabled={busy}>
                  <Icon name="check" size={15} /> {busy ? '保存中…' : '保存'}
                </button>
                <button className="btn-ghost" onClick={() => setDraft(null)} disabled={busy}>
                  取消
                </button>
              </div>
            </>
          ) : current ? (
            <>
              <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>
                  <Icon name="code" size={16} /> 模板原文
                </span>
                <button className="btn-ghost" onClick={startEdit} disabled={busy}>
                  <Icon name="edit" size={15} /> 编辑
                </button>
              </div>
              <div style={{ margin: '10px 0', color: 'var(--text-muted)', fontSize: 13 }}>
                {current.description}
              </div>
              <div className="code-block">{current.template}</div>
            </>
          ) : (
            <div className="empty">点击左侧模板查看内容，或点击「新建」创建模板。</div>
          )}
        </div>
      </div>
    </div>
  )
}

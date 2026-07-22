/**
 * 应用根组件。
 *
 * 负责：
 *  - 顶部品牌栏与全局模型选择器；
 *  - 左侧导航（对话 / 文档 / 智能体 / 记忆 / 提示工程）；
 *  - 后端健康状态轮询与展示；
 *  - 根据当前选中的功能页渲染对应面板。
 */
import { useEffect, useState } from 'react'
import { api } from './api/client'
import type { SelectedModel } from './types'
import Icon, { type IconName } from './components/Icon'
import ModelSelector from './components/ModelSelector'
import ChatPanel from './components/ChatPanel'
import DocumentsPanel from './components/DocumentsPanel'
import AgentPanel from './components/AgentPanel'
import MemoryPanel from './components/MemoryPanel'
import PromptPanel from './components/PromptPanel'
import GraphPanel from './components/GraphPanel'
import SettingsPanel from './components/SettingsPanel'

/** 功能页标识 */
type Tab = 'chat' | 'documents' | 'graph' | 'agent' | 'memory' | 'prompt' | 'settings'

/** 导航项配置 */
const NAV: { key: Tab; icon: IconName; label: string }[] = [
  { key: 'chat', icon: 'message', label: '智能对话' },
  { key: 'documents', icon: 'book', label: '知识库' },
  { key: 'graph', icon: 'graph', label: '知识图谱' },
  { key: 'agent', icon: 'cpu', label: '智能体' },
  { key: 'memory', icon: 'database', label: '记忆管理' },
  { key: 'prompt', icon: 'code', label: '提示工程' },
  { key: 'settings', icon: 'settings', label: '系统设置' },
]

export default function App() {
  const [tab, setTab] = useState<Tab>('chat')
  const [model, setModel] = useState<SelectedModel | null>(null)
  // 后端健康状态：null=检测中，true=正常，false=异常
  const [healthy, setHealthy] = useState<boolean | null>(null)

  // 挂载后立即检测一次，并每 15 秒轮询后端健康状态
  useEffect(() => {
    let timer: number
    const check = async () => {
      try {
        await api.health()
        setHealthy(true)
      } catch {
        setHealthy(false)
      }
    }
    check()
    timer = window.setInterval(check, 15000)
    return () => window.clearInterval(timer)
  }, [])

  return (
    <div className="app">
      <div className="app-body">
        {/* 左侧导航（内含品牌与模型选择） */}
        <nav className="sidebar">
          <div className="sidebar-brand">
            <h1>超级知识库平台</h1>
            <div className="subtitle">RAG · 智能体 · 记忆管理</div>
          </div>

          <div className="sidebar-model">
            <span className="sidebar-label">当前模型</span>
            <ModelSelector value={model} onChange={setModel} />
          </div>

          <div className="nav-group">
            {NAV.map((item) => (
              <button
                key={item.key}
                className={`nav-item ${tab === item.key ? 'active' : ''}`}
                onClick={() => setTab(item.key)}
              >
                <span className="icon">
                  <Icon name={item.icon} size={18} />
                </span>
                <span>{item.label}</span>
              </button>
            ))}
          </div>

          <div className="sidebar-footer">
            <span
              className={`status-dot ${healthy ? 'ok' : 'err'}`}
              title={healthy ? '后端服务正常' : '后端服务不可用'}
            />
            {healthy === null ? '检测中…' : healthy ? '服务正常' : '服务离线'}
          </div>
        </nav>

        {/* 主内容区：根据 tab 渲染对应面板 */}
        <main className="main">
          {tab === 'chat' && <ChatPanel model={model} />}
          {tab === 'documents' && <DocumentsPanel />}
          {tab === 'graph' && <GraphPanel model={model} />}
          {tab === 'agent' && <AgentPanel model={model} />}
          {tab === 'memory' && <MemoryPanel />}
          {tab === 'prompt' && <PromptPanel />}
          {tab === 'settings' && <SettingsPanel />}
        </main>
      </div>
    </div>
  )
}

import { Suspense, lazy, useEffect, useMemo, useState } from 'react'
import {
  App as AntApp,
  Badge,
  Button,
  ConfigProvider,
  Drawer,
  Grid,
  Layout,
  Menu,
  Spin,
  Tag,
  theme,
} from 'antd'
import ApiOutlined from '@ant-design/icons/ApiOutlined'
import BookOutlined from '@ant-design/icons/BookOutlined'
import BranchesOutlined from '@ant-design/icons/BranchesOutlined'
import DatabaseOutlined from '@ant-design/icons/DatabaseOutlined'
import ExperimentOutlined from '@ant-design/icons/ExperimentOutlined'
import MenuOutlined from '@ant-design/icons/MenuOutlined'
import MessageOutlined from '@ant-design/icons/MessageOutlined'
import RocketOutlined from '@ant-design/icons/RocketOutlined'
import SettingOutlined from '@ant-design/icons/SettingOutlined'
import { api } from './api/client'
import type { SelectedModel } from './types'
import ModelSelector from './components/ModelSelector'

const ChatPanel = lazy(() => import('./components/ChatPanel'))
const DocumentsPanel = lazy(() => import('./components/DocumentsPanel'))
const GraphPanel = lazy(() => import('./components/GraphPanel'))
const AgentPanel = lazy(() => import('./components/AgentPanel'))
const MemoryPanel = lazy(() => import('./components/MemoryPanel'))
const PromptPanel = lazy(() => import('./components/PromptPanel'))
const EvaluationPanel = lazy(() => import('./components/EvaluationPanel'))
const SettingsPanel = lazy(() => import('./components/SettingsPanel'))

type Tab = 'chat' | 'documents' | 'graph' | 'agent' | 'memory' | 'prompt' | 'evaluation' | 'settings'

const NAV = [
  { key: 'chat', icon: <MessageOutlined />, label: '智能对话', desc: 'RAG 问答与引用追溯' },
  { key: 'documents', icon: <BookOutlined />, label: '知识库', desc: '文档摄取与检索测试' },
  { key: 'graph', icon: <BranchesOutlined />, label: '知识图谱', desc: '实体关系可视化' },
  { key: 'agent', icon: <ApiOutlined />, label: '智能体', desc: '任务规划与工具调用' },
  { key: 'memory', icon: <DatabaseOutlined />, label: '记忆管理', desc: '会话与长期记忆' },
  { key: 'prompt', icon: <ExperimentOutlined />, label: '提示工程', desc: '模板编排与版本管理' },
  { key: 'evaluation', icon: <RocketOutlined />, label: '质量评估', desc: 'RAGAS 指标验证' },
  { key: 'settings', icon: <SettingOutlined />, label: '系统设置', desc: '模型、密钥与检索参数' },
] as const

function SidebarContent({ tab, onSelect, model, setModel, healthy }: {
  tab: Tab
  onSelect: (tab: Tab) => void
  model: SelectedModel | null
  setModel: (model: SelectedModel | null) => void
  healthy: boolean | null
}) {
  return (
    <>
      <div className="brand-block">
        <div className="brand-mark">AI</div>
        <div className="brand-title">超级知识库平台</div>
        <div className="brand-subtitle">Enterprise RAG Console</div>
      </div>
      <div className="sider-model">
        <span className="sider-label">当前模型</span>
        <ModelSelector value={model} onChange={setModel} dark />
      </div>
      <Menu
        className="app-menu"
        theme="dark"
        mode="inline"
        selectedKeys={[tab]}
        items={NAV.map((item) => ({ key: item.key, icon: item.icon, label: item.label }))}
        onClick={({ key }) => onSelect(key as Tab)}
      />
      <div className="sider-footer">
        <div className="status-row">
          <span className={`status-dot ${healthy ? 'ok' : healthy === false ? 'err' : ''}`} />
          <span>{healthy === null ? '检测后端服务中…' : healthy ? '后端服务正常' : '后端服务离线'}</span>
        </div>
      </div>
    </>
  )
}

export default function App() {
  const [tab, setTab] = useState<Tab>('chat')
  const [model, setModel] = useState<SelectedModel | null>(null)
  const [healthy, setHealthy] = useState<boolean | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const screens = Grid.useBreakpoint()
  const active = useMemo(() => NAV.find((item) => item.key === tab) ?? NAV[0], [tab])

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

  const selectTab = (next: Tab) => {
    setTab(next)
    setDrawerOpen(false)
  }

  const panel = (
    <Suspense fallback={<div style={{ minHeight: 420, display: 'grid', placeItems: 'center' }}><Spin size="large" /></div>}>
      {tab === 'chat' && <ChatPanel model={model} />}
      {tab === 'documents' && <DocumentsPanel />}
      {tab === 'graph' && <GraphPanel model={model} />}
      {tab === 'agent' && <AgentPanel model={model} />}
      {tab === 'memory' && <MemoryPanel />}
      {tab === 'prompt' && <PromptPanel />}
      {tab === 'evaluation' && <EvaluationPanel />}
      {tab === 'settings' && <SettingsPanel />}
    </Suspense>
  )

  return (
    <ConfigProvider
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: '#4f63ff',
          colorInfo: '#4f63ff',
          colorSuccess: '#16a34a',
          colorWarning: '#d97706',
          colorError: '#dc2626',
          borderRadius: 12,
          fontFamily: 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
        },
        components: {
          Layout: { siderBg: '#111a31', triggerBg: '#111a31' },
          Menu: { darkItemBg: 'transparent', darkSubMenuItemBg: 'transparent' },
          Card: { paddingLG: 20 },
        },
      }}
    >
      <AntApp>
        <Layout className="app-shell">
          {screens.md ? (
            <Layout.Sider width={264} className="app-sider desktop-sider">
              <SidebarContent tab={tab} onSelect={selectTab} model={model} setModel={setModel} healthy={healthy} />
            </Layout.Sider>
          ) : (
            <Drawer placement="left" width={286} open={drawerOpen} onClose={() => setDrawerOpen(false)} closable={false}>
              <SidebarContent tab={tab} onSelect={selectTab} model={model} setModel={setModel} healthy={healthy} />
            </Drawer>
          )}
          <Layout className="app-main-layout">
            <Layout.Header className="app-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
                <Button className="mobile-menu-btn" icon={<MenuOutlined />} onClick={() => setDrawerOpen(true)} />
                <div>
                  <div className="header-title">{active.label}</div>
                  <div className="header-subtitle">{active.desc}</div>
                </div>
              </div>
              <div className="header-actions">
                <Tag color={model ? 'success' : 'warning'}>{model ? `${model.provider}/${model.model}` : '未选择模型'}</Tag>
                <Badge status={healthy ? 'success' : healthy === false ? 'error' : 'processing'} text={healthy === null ? '连接中' : healthy ? '在线' : '离线'} />
              </div>
            </Layout.Header>
            <Layout.Content className="app-content">
              <div className="content-inner">{panel}</div>
            </Layout.Content>
          </Layout>
        </Layout>
      </AntApp>
    </ConfigProvider>
  )
}

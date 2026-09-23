/**
 * 应用根组件。
 *
 * 负责：
 *  - Ant Design 主题桥：ConfigProvider 按 data-theme 切换 default/dark 算法；
 *  - 左侧导航（antd Menu）+ 品牌区 + 全局模型选择器；
 *  - 后端健康状态轮询与展示；
 *  - 根据当前选中的功能页渲染对应面板。
 */
import { lazy, Suspense, useEffect, useState } from 'react'
import {
  App as AntApp,
  Badge,
  Button,
  ConfigProvider,
  Layout,
  Menu,
  theme as antdTheme,
  Tooltip,
} from 'antd'
import {
  ApiOutlined,
  BookOutlined,
  CodeOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  GlobalOutlined,
  MoonOutlined,
  PartitionOutlined,
  RobotOutlined,
  SettingOutlined,
  SunOutlined,
} from '@ant-design/icons'
import zhCN from 'antd/locale/zh_CN'
import { api } from './api/client'
import type { SelectedModel } from './types'
import ModelSelector from './components/ModelSelector'
import ChatPanel from './components/ChatPanel'
import { FlipText } from '@/components/block/flip-text'
import { RipplePulseLoader } from '@/components/ui/ripple-pulse-loader'

// 各功能面板按需加载（antd 组件体量较大，懒加载显著降低首屏开销）
const DocumentsPanel = lazy(() => import('./components/DocumentsPanel'))
const AgentPanel = lazy(() => import('./components/AgentPanel'))
const MemoryPanel = lazy(() => import('./components/MemoryPanel'))
const PromptPanel = lazy(() => import('./components/PromptPanel'))
const GraphPanel = lazy(() => import('./components/GraphPanel'))
const SettingsPanel = lazy(() => import('./components/SettingsPanel'))
const EvaluationPanel = lazy(() => import('./components/EvaluationPanel'))
const EmbedPanel = lazy(() => import('./components/EmbedPanel'))

/** 功能页标识 */
type Tab =
  | 'chat'
  | 'documents'
  | 'embed'
  | 'graph'
  | 'agent'
  | 'memory'
  | 'prompt'
  | 'evaluation'
  | 'settings'

/** 导航项配置 */
const NAV_ITEMS = [
  { key: 'chat', icon: <ApiOutlined />, label: '智能对话' },
  { key: 'documents', icon: <BookOutlined />, label: '知识库' },
  { key: 'embed', icon: <GlobalOutlined />, label: '嵌入集成' },
  { key: 'graph', icon: <PartitionOutlined />, label: '知识图谱' },
  { key: 'agent', icon: <RobotOutlined />, label: '智能体' },
  { key: 'memory', icon: <DatabaseOutlined />, label: '记忆管理' },
  { key: 'prompt', icon: <CodeOutlined />, label: '提示工程' },
  { key: 'evaluation', icon: <DashboardOutlined />, label: '质量评估' },
  { key: 'settings', icon: <SettingOutlined />, label: '系统设置' },
]

/** 读取初始主题：本地存储优先，否则跟随系统偏好 */
function initialTheme(): 'light' | 'dark' {
  const saved = localStorage.getItem('ragkb_theme')
  if (saved === 'dark' || saved === 'light') return saved
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function Shell() {
  const [tab, setTab] = useState<Tab>('chat')
  const [model, setModel] = useState<SelectedModel | null>(null)
  const [theme, setTheme] = useState<'light' | 'dark'>(initialTheme)
  // 后端健康状态：null=检测中，true=正常，false=异常
  const [healthy, setHealthy] = useState<boolean | null>(null)
  const { token } = antdTheme.useToken()

  // 主题生效并持久化
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('ragkb_theme', theme)
  }, [theme])

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
    <Layout style={{ height: '100vh' }}>
      <Layout.Sider
        width={232}
        theme={theme === 'dark' ? 'dark' : 'light'}
        style={{
          borderRight: `1px solid ${token.colorBorderSecondary}`,
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* 品牌区 */}
        <div style={{ padding: '18px 16px 14px', borderBottom: `1px solid ${token.colorBorderSecondary}` }}>
          <div
            style={{
              fontSize: 17,
              fontWeight: 700,
              letterSpacing: '-0.01em',
            }}
          >
            <FlipText duration={1.8} className="brand-flip">
              超级知识库平台
            </FlipText>
          </div>
          <div style={{ fontSize: 11.5, color: token.colorTextTertiary, marginTop: 3 }}>
            RAG · 智能体 · 记忆管理
          </div>
        </div>

        {/* 模型选择器 */}
        <div style={{ padding: '12px 16px 8px' }}>
          <div
            style={{
              fontSize: 11,
              fontWeight: 600,
              letterSpacing: '0.04em',
              textTransform: 'uppercase',
              color: token.colorTextTertiary,
              marginBottom: 6,
            }}
          >
            当前模型
          </div>
          <ModelSelector value={model} onChange={setModel} />
        </div>

        {/* 导航菜单 */}
        <Menu
          mode="inline"
          theme={theme === 'dark' ? 'dark' : 'light'}
          selectedKeys={[tab]}
          items={NAV_ITEMS}
          onClick={({ key }) => setTab(key as Tab)}
          style={{ flex: 1, borderRight: 'none', overflow: 'auto' }}
        />

        {/* 底部：健康状态 + 主题切换 */}
        <div
          style={{
            padding: '12px 16px',
            borderTop: `1px solid ${token.colorBorderSecondary}`,
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            fontSize: 12,
            color: token.colorTextTertiary,
          }}
        >
          <Badge
            status={healthy === null ? 'default' : healthy ? 'success' : 'error'}
            text={healthy === null ? '检测中…' : healthy ? '服务正常' : '服务离线'}
          />
          <Tooltip title={theme === 'dark' ? '切换浅色模式' : '切换深色模式'}>
            <Button
              type="text"
              size="small"
              icon={theme === 'dark' ? <SunOutlined /> : <MoonOutlined />}
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              style={{ marginLeft: 'auto' }}
              aria-label="切换主题"
            />
          </Tooltip>
        </div>
      </Layout.Sider>

      {/* 主内容区：根据 tab 渲染对应面板 */}
      <Layout.Content style={{ overflowY: 'auto', padding: '28px 32px' }}>
        <Suspense
          fallback={
            <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}>
              <RipplePulseLoader size={120} />
            </div>
          }
        >
          {tab === 'chat' && <ChatPanel model={model} />}
          {tab === 'documents' && <DocumentsPanel />}
          {tab === 'agent' && <AgentPanel model={model} />}
          {tab === 'memory' && <MemoryPanel />}
          {tab === 'prompt' && <PromptPanel />}
          {tab === 'embed' && <EmbedPanel />}
          {tab === 'graph' && <GraphPanel model={model} />}
          {tab === 'evaluation' && <EvaluationPanel />}
          {tab === 'settings' && <SettingsPanel />}
        </Suspense>
      </Layout.Content>
    </Layout>
  )
}

export default function App() {
  const [theme] = useState<'light' | 'dark'>(initialTheme)
  // 顶层主题状态：Shell 内部切换通过订阅 data-theme 变化
  const [current, setCurrent] = useState<'light' | 'dark'>(theme)

  // 监听 html[data-theme] 变化（Shell 内部写入），同步 antd 算法
  useEffect(() => {
    const observer = new MutationObserver(() => {
      const t = document.documentElement.dataset.theme
      if (t === 'dark' || t === 'light') setCurrent(t)
    })
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => observer.disconnect()
  }, [])

  const isDark = current === 'dark'

  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: isDark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
        token: {
          colorPrimary: isDark ? '#5b8def' : '#2563eb',
          colorInfo: isDark ? '#5b8def' : '#2563eb',
          borderRadius: 8,
          colorBgLayout: isDark ? '#0d1117' : '#e7e9ee',
          colorBgContainer: isDark ? '#151b24' : '#fafbfc',
        },
      }}
    >
      <AntApp>
        <Shell />
      </AntApp>
    </ConfigProvider>
  )
}

/// <reference types="vite/client" />

// react-cytoscapejs 未提供官方类型声明，在此最小化声明组件类型。
declare module 'react-cytoscapejs' {
  import type { CSSProperties } from 'react'
  import type { Core, ElementDefinition, LayoutOptions, Stylesheet } from 'cytoscape'

  interface CytoscapeComponentProps {
    elements: ElementDefinition[]
    style?: CSSProperties
    stylesheet?: Stylesheet[]
    layout?: LayoutOptions
    cy?: (cy: Core) => void
    className?: string
    minZoom?: number
    maxZoom?: number
  }

  const CytoscapeComponent: (props: CytoscapeComponentProps) => JSX.Element
  export default CytoscapeComponent
}

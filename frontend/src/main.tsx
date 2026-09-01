/**
 * 文件功能：前端应用入口文件
 * 文件描述：负责将 React 应用挂载到 index.html 中的 #root 节点，并引入全局样式
 * 核心逻辑：使用 ReactDOM.createRoot 创建根节点，以 React.StrictMode 包裹 App 组件进行渲染，
 *          StrictMode 用于在开发环境下提前发现潜在问题（如副作用不纯等）
 */
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)

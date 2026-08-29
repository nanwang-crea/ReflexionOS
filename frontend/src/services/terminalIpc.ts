// 文件功能：终端 IPC（进程间通信）能力的前端封装
// 文件描述：封装与 Electron 主进程之间的终端相关 IPC 调用（创建/写入/缩放/终止/存活检测/
//           数据与退出事件监听），供渲染进程中的终端组件使用
// 核心逻辑：所有方法先通过 isElectronRuntime 判断是否处于桌面端环境，
//           非 Electron 环境（如纯浏览器）下静默降级（返回 false/undefined 或空操作函数），
//           避免终端功能在不支持的平台上抛出异常
import { isElectronRuntime } from './desktopClient'

/**
 * 函数名：getApi
 * 入参：无
 * 功能：获取 Electron 预加载脚本注入的终端 IPC API
 * 运行逻辑：先判断是否处于 Electron 运行时，不是则直接返回 null；
 *           是则读取 window.electronAPI.terminal，不存在时同样返回 null
 * 出参：终端 IPC API 对象或 null（非桌面端环境时）
 */
function getApi() {
  if (!isElectronRuntime()) {
    return null
  }
  return window.electronAPI?.terminal ?? null
}

// terminalIpc：对外暴露的终端 IPC 调用集合，内部统一处理不可用环境的降级
export const terminalIpc = {
  /**
   * 函数名：isAvailable
   * 入参：无
   * 功能：判断终端 IPC 能力当前是否可用
   * 运行逻辑：调用 getApi，能取到 API 实例即视为可用
   * 出参：boolean - true 表示终端功能可用（处于 Electron 环境）
   */
  isAvailable(): boolean {
    return getApi() !== null
  },

  /**
   * 函数名：create
   * 入参：
   *   - id (string): 终端会话唯一标识
   *   - cwd (string): 终端启动的工作目录（不同平台路径分隔符由操作系统/Node 决定）
   * 功能：在主进程中创建一个新的终端进程
   * 运行逻辑：获取 IPC API，不可用时抛出错误；可用时委托主进程创建终端并返回其 pid
   * 出参：Promise<{ pid: number }> - 新建终端进程的进程号
   */
  async create(id: string, cwd: string): Promise<{ pid: number }> {
    const api = getApi()
    if (!api) throw new Error('Terminal IPC not available')
    return api.create(id, cwd)
  },

  /**
   * 函数名：write
   * 入参：
   *   - id (string): 终端会话标识
   *   - data (string): 要写入终端的数据（如用户输入）
   * 功能：向指定终端进程写入数据
   * 运行逻辑：获取 IPC API，不可用时静默返回（不抛错）；可用时转发写入请求
   * 出参：Promise<void>
   */
  async write(id: string, data: string): Promise<void> {
    const api = getApi()
    if (!api) return
    return api.write(id, data)
  },

  /**
   * 函数名：resize
   * 入参：
   *   - id (string): 终端会话标识
   *   - cols (number): 终端列数
   *   - rows (number): 终端行数
   * 功能：调整指定终端的显示尺寸（行列数）
   * 运行逻辑：获取 IPC API，不可用时静默返回；可用时转发尺寸调整请求
   * 出参：Promise<void>
   */
  async resize(id: string, cols: number, rows: number): Promise<void> {
    const api = getApi()
    if (!api) return
    return api.resize(id, cols, rows)
  },

  /**
   * 函数名：kill
   * 入参：
   *   - id (string): 终端会话标识
   * 功能：终止指定的终端进程
   * 运行逻辑：获取 IPC API，不可用时静默返回；可用时转发终止请求
   * 出参：Promise<void>
   */
  async kill(id: string): Promise<void> {
    const api = getApi()
    if (!api) return
    return api.kill(id)
  },

  /**
   * 函数名：isAlive
   * 入参：
   *   - id (string): 终端会话标识
   * 功能：查询指定终端进程是否仍存活
   * 运行逻辑：获取 IPC API，不可用时返回 false；可用时转发查询请求
   * 出参：Promise<boolean> - true 表示终端进程仍在运行
   */
  async isAlive(id: string): Promise<boolean> {
    const api = getApi()
    if (!api) return false
    return api.isAlive(id)
  },

  /**
   * 函数名：onData
   * 入参：
   *   - callback ((id: string, data: string) => void): 终端有新数据输出时的回调
   * 功能：订阅终端数据输出事件
   * 运行逻辑：获取 IPC API，不可用时返回一个空操作的取消订阅函数（保证调用方无需判空）；
   *           可用时转发订阅请求并返回其提供的取消订阅函数
   * 出参：() => void - 用于取消订阅的函数
   */
  onData(callback: (id: string, data: string) => void): () => void {
    const api = getApi()
    if (!api) return () => {}
    return api.onData(callback)
  },

  /**
   * 函数名：onExit
   * 入参：
   *   - callback ((id: string, exitCode: number) => void): 终端进程退出时的回调
   * 功能：订阅终端进程退出事件
   * 运行逻辑：获取 IPC API，不可用时返回空操作的取消订阅函数；
   *           可用时转发订阅请求并返回其提供的取消订阅函数
   * 出参：() => void - 用于取消订阅的函数
   */
  onExit(callback: (id: string, exitCode: number) => void): () => void {
    const api = getApi()
    if (!api) return () => {}
    return api.onExit(callback)
  },
}

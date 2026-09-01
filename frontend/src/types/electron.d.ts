// 文件功能：Electron 渲染进程全局类型声明
// 文件描述：为 window.electronAPI（由 Electron 主进程通过 preload 脚本注入）声明类型，
//          使渲染进程（前端页面）代码在调用这些桌面端专属能力时能获得类型检查与自动补全
// 核心逻辑：仅在 Electron 环境下 electronAPI 才存在（浏览器环境下为 undefined），
//          因此声明为可选属性，调用前需自行判断 isElectron / electronAPI 是否存在
export {}

declare global {
  interface Window {
    electronAPI?: {
      // 是否运行在 Electron 桌面端环境中（区别于纯浏览器环境）
      isElectron: boolean
      // 弹出系统目录选择对话框，返回用户选择的目录路径；用户取消则返回 null
      selectDirectory: () => Promise<string | null>
      // 查询由 Electron 主进程托管的后端服务状态（运行状态、访问地址、进程号等）
      getBackendStatus: () => Promise<{ state: string; url: string; pid: number | null; managed: boolean; error: string | null }>
      // 终端相关能力：由主进程创建/管理伪终端（pty），供前端内嵌终端组件调用
      terminal: {
        // 创建一个新终端会话：id 为终端标识，cwd 为初始工作目录；返回该终端进程的 pid
        create: (id: string, cwd: string) => Promise<{ pid: number }>
        // 向指定终端写入输入数据（如用户键入的字符）
        write: (id: string, data: string) => Promise<void>
        // 调整指定终端的显示尺寸（列数/行数），用于窗口大小变化时同步终端渲染尺寸
        resize: (id: string, cols: number, rows: number) => Promise<void>
        // 终止并清理指定终端进程
        kill: (id: string) => Promise<void>
        // 查询指定终端进程是否仍存活
        isAlive: (id: string) => Promise<boolean>
        // 订阅终端输出数据事件；返回取消订阅函数
        onData: (callback: (id: string, data: string) => void) => () => void
        // 订阅终端进程退出事件（携带退出码）；返回取消订阅函数
        onExit: (callback: (id: string, exitCode: number) => void) => () => void
      }
    }
  }
}

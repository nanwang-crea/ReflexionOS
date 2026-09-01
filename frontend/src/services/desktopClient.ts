// 文件功能：桌面端（Electron）运行环境的判断与原生能力调用封装
// 文件描述：通过 window.electronAPI（由 Electron 预加载脚本注入）判断当前是否运行在
//           桌面客户端中，并封装选择本地项目目录这一原生对话框能力；
//           在纯浏览器环境下 window.electronAPI 不存在，相关调用会安全降级
// 核心逻辑：所有函数均对 window.electronAPI 做可选链判断，避免在 Web 端访问 undefined 报错

/**
 * 函数名：isElectronRuntime
 * 入参：无
 * 功能：判断当前代码是否运行在 Electron 桌面客户端环境中
 * 运行逻辑：读取 window.electronAPI.isElectron 标志位，仅当其严格等于 true 时判定为桌面端；
 *           浏览器环境下 window.electronAPI 为 undefined，可选链会返回 undefined，从而判定为 false
 * 出参：boolean - true 表示当前处于 Electron 桌面端，false 表示浏览器等其他环境
 */
export function isElectronRuntime() {
  return window.electronAPI?.isElectron === true
}

/**
 * 函数名：selectProjectDirectory
 * 入参：无
 * 功能：调用 Electron 原生目录选择对话框，让用户选择本地项目目录
 * 运行逻辑：委托给 window.electronAPI.selectDirectory()（由主进程实现的原生文件对话框）；
 *           若当前不在 Electron 环境（该 API 不存在），则直接返回已兑现为 null 的 Promise，
 *           调用方无需区分平台即可统一处理返回值
 * 出参：Promise<string | null> - 用户选择的目录路径（不同平台路径分隔符由操作系统决定），
 *       用户取消选择或非桌面端环境时返回 null
 */
export function selectProjectDirectory() {
  return window.electronAPI?.selectDirectory() ?? Promise.resolve(null)
}

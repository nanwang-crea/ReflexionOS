/**
 * 文件功能：会话记录（transcript）自动滚动判定逻辑
 * 文件描述：根据滚动容器当前位置判断是否应自动跟随滚动到底部，用于新消息/流式输出时的自动滚屏。
 * 核心逻辑：距底部距离小于等于阈值（100px）时认为应跟随滚动，避免用户主动上翻查看历史时被打断。
 */
// 判定“跟随滚动”的阈值：距离底部小于等于该像素值时，视为用户仍在关注最新内容
export const AUTO_SCROLL_FOLLOW_THRESHOLD_PX = 100

/**
 * 函数名：shouldFollowTranscript
 * 入参：
 *   - position ({ scrollTop, clientHeight, scrollHeight }): 滚动容器的当前滚动位置信息
 *     scrollTop 为已滚动距离，clientHeight 为可视区域高度，scrollHeight 为内容总高度
 * 功能：判断当前滚动位置是否应自动跟随滚动到底部
 * 运行逻辑：计算当前位置距离容器底部的像素距离（scrollHeight - (scrollTop + clientHeight)），
 *          若该距离小于等于 AUTO_SCROLL_FOLLOW_THRESHOLD_PX 则返回 true，否则返回 false
 * 出参：boolean - true 表示应自动滚动跟随到底部，false 表示不应打断用户当前的浏览位置
 */
export function shouldFollowTranscript(position: {
  scrollTop: number
  clientHeight: number
  scrollHeight: number
}): boolean {
  const distanceFromBottom = position.scrollHeight - (position.scrollTop + position.clientHeight)
  return distanceFromBottom <= AUTO_SCROLL_FOLLOW_THRESHOLD_PX
}

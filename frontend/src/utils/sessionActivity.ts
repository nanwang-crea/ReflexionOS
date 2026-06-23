// 会话未读活动派生：以事件序号（last_event_seq）为基线，而非时间戳。
// 某会话的最新事件序号超过“用户最后看到的序号”，即视为有未读活动。
// 这是纯函数，供 sidebar 等多处按会话统一派生未读状态，避免各自造轮子。

/**
 * 判断某会话是否有未读活动。
 *
 * @param lastEventSeq 会话当前最新事件序号（来自 conversation 真值）
 * @param lastSeenEventSeq 用户最后看到该会话时记录的序号（持久化在 workspace.store）
 */
export function hasUnreadActivity(
  lastEventSeq: number | undefined,
  lastSeenEventSeq: number | undefined,
): boolean {
  const latest = lastEventSeq ?? 0
  const seen = lastSeenEventSeq ?? 0
  return latest > seen
}

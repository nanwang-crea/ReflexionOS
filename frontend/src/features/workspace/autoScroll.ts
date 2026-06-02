export const AUTO_SCROLL_FOLLOW_THRESHOLD_PX = 100

export function shouldFollowTranscript(position: {
  scrollTop: number
  clientHeight: number
  scrollHeight: number
}): boolean {
  const distanceFromBottom = position.scrollHeight - (position.scrollTop + position.clientHeight)
  return distanceFromBottom <= AUTO_SCROLL_FOLLOW_THRESHOLD_PX
}

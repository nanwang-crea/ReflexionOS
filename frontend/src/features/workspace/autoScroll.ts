export const AUTO_SCROLL_FOLLOW_THRESHOLD_PX = 80

export function shouldFollowTranscript(position: {
  scrollTop: number
  clientHeight: number
  scrollHeight: number
}): boolean {
  const distanceFromBottom = position.scrollHeight - (position.scrollTop + position.clientHeight)
  return distanceFromBottom <= AUTO_SCROLL_FOLLOW_THRESHOLD_PX
}

export const MIN_RECEIPT_VISIBLE_MS = 120

export function getReceiptFinalizeDelay(
  visibleAt: number | null,
  now: number,
  minVisibleMs = MIN_RECEIPT_VISIBLE_MS
) {
  if (visibleAt === null) {
    return 0
  }

  const elapsed = now - visibleAt
  return elapsed >= minVisibleMs ? 0 : minVisibleMs - elapsed
}

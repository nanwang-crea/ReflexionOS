interface LoadMoreButtonProps {
  hasMore: boolean
  onClick: () => void
}

export default function LoadMoreButton({ hasMore, onClick }: LoadMoreButtonProps) {
  if (!hasMore) return null

  return (
    <div className="mt-8 flex justify-center">
      <button
        onClick={onClick}
        className="rounded-2xl border border-edge bg-surface-tertiary px-6 py-3 text-sm font-medium text-content-primary transition-colors hover:bg-surface-secondary"
      >
        加载更多
      </button>
    </div>
  )
}

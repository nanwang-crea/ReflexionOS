import type { ConversationMessage } from '@/types/conversation'

function toJson(value: unknown) {
  if (value === undefined) {
    return null
  }

  try {
    return JSON.stringify(value, null, 2)
  } catch (_error) {
    return String(value)
  }
}

function formatDuration(duration: unknown) {
  if (typeof duration !== 'number' || !Number.isFinite(duration)) {
    return null
  }

  return `${duration}ms`
}

export function ToolTraceCard({ message }: { message: ConversationMessage }) {
  const payload = message.payloadJson
  const toolName = typeof payload.tool_name === 'string' ? payload.tool_name : 'tool'
  const status = typeof payload.status === 'string'
    ? payload.status
    : message.streamState === 'failed'
      ? 'failed'
      : message.streamState
  const argumentsJson = toJson(payload.arguments)
  const output = toJson(payload.output)
  const error = typeof payload.error === 'string' ? payload.error : null
  const duration = formatDuration(payload.duration)

  return (
    <div className="mb-6 rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
        <span className="font-semibold text-slate-800">{toolName}</span>
        <span>{status}</span>
        {duration && <span>· {duration}</span>}
      </div>

      {argumentsJson && (
        <pre className="mt-3 overflow-x-auto rounded-lg bg-white p-3 text-xs text-slate-600">{argumentsJson}</pre>
      )}

      {output && (
        <pre className="mt-3 overflow-x-auto rounded-lg bg-white p-3 text-xs text-slate-700">{output}</pre>
      )}

      {error && (
        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {error}
        </div>
      )}
    </div>
  )
}

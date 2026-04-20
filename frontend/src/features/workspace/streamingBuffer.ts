export const LONG_STREAM_THRESHOLD = 1200

interface StreamingBufferOptions {
  onFlush: (value: string) => void
}

export function createStreamingBuffer({ onFlush }: StreamingBufferOptions) {
  let pending = ''
  let totalLength = 0

  return {
    push(chunk: string) {
      totalLength += chunk.length

      if (totalLength < LONG_STREAM_THRESHOLD) {
        onFlush(chunk)
        return
      }

      pending += chunk
    },

    flush() {
      if (!pending) {
        return
      }

      onFlush(pending)
      pending = ''
    },

    reset() {
      pending = ''
      totalLength = 0
    },
  }
}

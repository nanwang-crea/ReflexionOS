import { describe, expect, it, vi } from 'vitest'
import {
  createStreamingBuffer,
  LONG_STREAM_THRESHOLD,
} from './streamingBuffer'

describe('createStreamingBuffer', () => {
  it('flushes short content immediately', () => {
    const onFlush = vi.fn()
    const buffer = createStreamingBuffer({ onFlush })

    buffer.push('short')

    expect(onFlush).toHaveBeenCalledWith('short')
  })

  it('buffers long content and flushes batched updates', () => {
    const onFlush = vi.fn()
    const buffer = createStreamingBuffer({ onFlush })
    const longToken = 'x'.repeat(LONG_STREAM_THRESHOLD)

    buffer.push(longToken)

    expect(onFlush).not.toHaveBeenCalled()

    buffer.flush()

    expect(onFlush).toHaveBeenCalledWith(longToken)
  })
})

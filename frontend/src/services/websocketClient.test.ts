import { describe, expect, it } from 'vitest'
import { buildExecutionStartMessage } from './websocketClient'

describe('buildExecutionStartMessage', () => {
  it('sends project_path instead of overloading project_id semantics', () => {
    expect(
      buildExecutionStartMessage('Run task', '/tmp/reflexion', 'provider-a', 'model-a')
    ).toEqual({
      type: 'start',
      data: {
        task: 'Run task',
        project_path: '/tmp/reflexion',
        provider_id: 'provider-a',
        model_id: 'model-a',
      },
    })
  })
})

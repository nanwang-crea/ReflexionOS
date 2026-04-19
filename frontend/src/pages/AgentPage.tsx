import { useState, useEffect } from 'react'
import { agentApi, llmApi } from '@/services/apiClient'
import { useProjectStore } from '@/stores/projectStore'
import { useAgentStore } from '@/stores/agentStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { Execution } from '@/types/execution'

export default function AgentPage() {
  const { currentProject } = useProjectStore()
  const { task, setTask, setExecutionStatus, reset } = useAgentStore()
  const {
    configured,
    defaultProviderId,
    defaultModelId,
    loaded,
    setLLMState,
  } = useSettingsStore()
  const [execution, setExecution] = useState<Execution | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    const loadSettings = async () => {
      try {
        const [providersResponse, defaultResponse] = await Promise.all([
          llmApi.getProviders(),
          llmApi.getDefaultSelection(),
        ])

        if (cancelled) {
          return
        }

        setLLMState({
          providers: providersResponse.data,
          selection: defaultResponse.data,
        })
      } catch (loadError) {
        console.error('Failed to load LLM settings:', loadError)
      }
    }

    loadSettings()

    return () => {
      cancelled = true
    }
  }, [setLLMState])

  const handleExecute = async () => {
    if (!currentProject) {
      setError('Please select a project first')
      return
    }
    if (!task.trim()) {
      setError('Please enter a task')
      return
    }
    if (!configured) {
      setError('Please configure LLM settings first')
      return
    }

    setLoading(true)
    setError(null)
    setExecutionStatus('running')

    try {
      const response = await agentApi.execute({
        project_id: currentProject.path,
        task: task,
        provider_id: defaultProviderId || undefined,
        model_id: defaultModelId || undefined,
      })
      setExecution(response.data)
      setExecutionStatus(response.data.status)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to execute task')
      setExecutionStatus('failed')
    } finally {
      setLoading(false)
    }
  }

  const handleReset = () => {
    reset()
    setExecution(null)
    setError(null)
  }

  return (
    <div className="p-8">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Agent</h2>

      {!configured && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-6">
          <p className="text-yellow-800">
            Please configure providers, models, and a default selection in the Settings page before using the agent.
          </p>
        </div>
      )}

      <div className="bg-white rounded-lg border border-gray-200 p-6 mb-6">
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Current Project
          </label>
          {currentProject ? (
            <div className="p-3 bg-gray-50 rounded-lg">
              <span className="font-medium">{currentProject.name}</span>
              <span className="text-gray-500 ml-2">{currentProject.path}</span>
            </div>
          ) : (
            <div className="p-3 bg-gray-50 rounded-lg text-gray-500">
              No project selected. Please select a project from the Projects page.
            </div>
          )}
        </div>

        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">Task</label>
          <textarea
            value={task}
            onChange={(e) => setTask(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg h-32"
            placeholder="Describe what you want the agent to do..."
            disabled={loading}
          />
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700">
            {error}
          </div>
        )}

        <div className="flex gap-3">
          <button
            onClick={handleExecute}
            disabled={loading || !configured || !loaded}
            className={`px-4 py-2 rounded-lg ${
              loading || !configured || !loaded
                ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                : 'bg-blue-600 text-white hover:bg-blue-700'
            }`}
          >
            {loading ? 'Executing...' : 'Execute'}
          </button>
          <button
            onClick={handleReset}
            className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
          >
            Reset
          </button>
        </div>
      </div>

      {execution && (
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-semibold">Execution Result</h3>
            <span
              className={`px-3 py-1 rounded-full text-sm ${
                execution.status === 'completed'
                  ? 'bg-green-100 text-green-700'
                  : execution.status === 'failed'
                  ? 'bg-red-100 text-red-700'
                  : 'bg-blue-100 text-blue-700'
              }`}
            >
              {execution.status}
            </span>
          </div>

          <div className="mb-4">
            <p className="text-sm text-gray-500">Task: {execution.task}</p>
            {execution.total_duration && (
              <p className="text-sm text-gray-500">
                Duration: {(execution.total_duration).toFixed(2)}s
              </p>
            )}
          </div>

          {execution.steps.length > 0 && (
            <div>
              <h4 className="font-medium mb-2">Steps ({execution.steps.length})</h4>
              <div className="space-y-2">
                {execution.steps.map((step, index) => (
                  <div key={step.id} className="border border-gray-200 rounded-lg p-3">
                    <div className="flex justify-between items-center mb-2">
                      <span className="font-medium">Step {index + 1}: {step.tool}</span>
                      <span
                        className={`px-2 py-0.5 rounded text-xs ${
                          step.status === 'success'
                            ? 'bg-green-100 text-green-700'
                            : 'bg-red-100 text-red-700'
                        }`}
                      >
                        {step.status}
                      </span>
                    </div>
                    {step.output && (
                      <pre className="text-sm bg-gray-50 p-2 rounded overflow-auto max-h-32">
                        {step.output}
                      </pre>
                    )}
                    {step.error && (
                      <p className="text-sm text-red-600">{step.error}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {execution.result && (
            <div className="mt-4">
              <h4 className="font-medium mb-2">Result</h4>
              <p className="bg-gray-50 p-3 rounded-lg">{execution.result}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

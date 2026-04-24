import type { DefaultLLMSelection, ProviderInstance } from '@/types/llm'
import type { Project } from '@/types/project'
import type { SessionSummary } from '@/types/workspace'
import type { WorkspaceUiState } from '@/stores/workspaceStore'

function createIso(offsetMinutes = 0) {
  return new Date(Date.now() - offsetMinutes * 60 * 1000).toISOString()
}

export function isDemoMode() {
  if (typeof window === 'undefined') {
    return false
  }

  return new URLSearchParams(window.location.search).get('demo') === '1'
}

export const demoProjects: Project[] = [
  {
    id: 'demo-proj-reflexion',
    name: 'ReflexionOS',
    path: '/workspace/reflexion-os',
    language: 'typescript',
    created_at: createIso(1800),
    updated_at: createIso(8),
  },
  {
    id: 'demo-proj-runtime',
    name: 'agent-runtime-framework',
    path: '/workspace/agent-runtime-framework',
    language: 'python',
    created_at: createIso(2400),
    updated_at: createIso(36),
  },
  {
    id: 'demo-proj-playground',
    name: 'playground',
    path: '/workspace/playground',
    language: 'rust',
    created_at: createIso(3200),
    updated_at: createIso(120),
  },
]

export const demoCurrentProject = demoProjects[0]

export const demoSessions: SessionSummary[] = [
  {
    id: 'demo-session-desktop',
    projectId: 'demo-proj-reflexion',
    title: 'Harden Electron bootstrap',
    preferredProviderId: 'demo-provider-openai',
    preferredModelId: 'demo-model-qwen',
    createdAt: createIso(60),
    updatedAt: createIso(4),
  },
  {
    id: 'demo-session-receipts',
    projectId: 'demo-proj-reflexion',
    title: 'Stream execution receipts in chat',
    createdAt: createIso(180),
    updatedAt: createIso(48),
  },
  {
    id: 'demo-session-runtime',
    projectId: 'demo-proj-runtime',
    title: 'Audit tool registry flow',
    createdAt: createIso(260),
    updatedAt: createIso(130),
  },
]

export const demoWorkspaceState: WorkspaceUiState = {
  currentSessionId: 'demo-session-desktop',
  expandedProjectIds: ['demo-proj-reflexion', 'demo-proj-runtime'],
  expandedSessionProjectIds: [],
  searchQuery: '',
  searchOpen: false,
}

export const demoProviders: ProviderInstance[] = [
  {
    id: 'demo-provider-openai',
    name: 'OpenAI 官方',
    provider_type: 'openai_compatible',
    api_key: 'demo-key',
    base_url: 'https://api.openai.com/v1',
    default_model_id: 'demo-model-qwen',
    enabled: true,
    models: [
      {
        id: 'demo-model-qwen',
        display_name: 'Qwen 3.6 Plus',
        model_name: 'qwen3.6-plus',
        enabled: true,
      },
      {
        id: 'demo-model-gpt41',
        display_name: 'GPT-4.1',
        model_name: 'gpt-4.1',
        enabled: true,
      },
    ],
  },
]

export const demoDefaultLLMSelection: DefaultLLMSelection = {
  provider_id: 'demo-provider-openai',
  model_id: 'demo-model-qwen',
  configured: true,
}

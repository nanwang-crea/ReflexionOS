import type { ActionReceiptDetail } from '@/components/execution/receiptUtils'
import type { DefaultLLMSelection, ProviderInstance } from '@/types/llm'
import type { Project } from '@/types/project'
import type { SessionSummary, WorkspaceSessionRound } from '@/types/workspace'
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

const workspaceReceiptDetails: ActionReceiptDetail[] = [
  {
    id: 'demo-detail-1',
    toolName: 'file',
    status: 'success',
    summary: '探索 electron/main.cjs',
    category: 'explore',
    target: 'electron/main.cjs',
  },
  {
    id: 'demo-detail-2',
    toolName: 'file',
    status: 'success',
    summary: '探索 electron/backend-manager.cjs',
    category: 'explore',
    target: 'electron/backend-manager.cjs',
  },
  {
    id: 'demo-detail-3',
    toolName: 'patch',
    status: 'success',
    summary: '编辑 electron/backend-manager.cjs',
    category: 'edit',
    target: 'electron/backend-manager.cjs',
  },
  {
    id: 'demo-detail-4',
    toolName: 'shell',
    status: 'success',
    summary: '运行 pnpm start',
    category: 'command',
    duration: 1.7,
  },
]

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

export const demoSessionHistoryById: Record<string, WorkspaceSessionRound[]> = {
  'demo-session-desktop': [
    {
      id: 'demo-round-1',
      createdAt: createIso(58),
      items: [
        {
          id: 'demo-user-1',
          type: 'user-message',
          content: 'Make the Electron desktop bootstrap more reliable and easier to inspect.',
        },
        {
          id: 'demo-update-1',
          type: 'agent-update',
          content: 'I checked the Electron entrypoint and the backend manager first so I could verify the full startup path before changing anything.',
        },
        {
          id: 'demo-receipt-1',
          type: 'action-receipt',
          receiptStatus: 'completed',
          details: workspaceReceiptDetails,
        },
        {
          id: 'demo-assistant-1',
          type: 'assistant-message',
          content: [
            'Updated the desktop bootstrap so the app is easier to start and diagnose.',
            '',
            '- The backend manager now prefers a Python interpreter that already has the required runtime packages.',
            '- Electron can start the local FastAPI backend and verify `/health` before opening the workspace.',
            '- The README now defaults to the desktop flow with `pnpm` commands.',
          ].join('\n'),
        },
      ],
    },
  ],
}

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

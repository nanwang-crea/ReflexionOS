import { normalizeRoundFromApi } from './sessionHistoryRound'
import { sessionApi } from './sessionApi'
import { useSessionStore } from './sessionStore'

export async function ensureProjectSessionsLoaded(projectId: string) {
  const response = await sessionApi.listProjectSessions(projectId)
  useSessionStore.getState().setProjectSessions(projectId, response.data)
}

export async function refreshSessionHistory(sessionId: string) {
  const response = await sessionApi.getSessionHistory(sessionId)
  useSessionStore.getState().setSessionHistory(
    sessionId,
    response.data.rounds.map((round) => normalizeRoundFromApi(round))
  )
}

export async function ensureSessionHistoryLoaded(sessionId: string) {
  if (useSessionStore.getState().historyBySessionId[sessionId]) {
    return
  }

  await refreshSessionHistory(sessionId)
}

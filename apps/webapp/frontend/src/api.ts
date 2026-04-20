import type { SessionPayload, SessionSummary } from "@/types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    ...init,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.error || detail;
    } catch {
      // ignore
    }
    throw new Error(`${response.status}: ${detail}`);
  }
  return (await response.json()) as T;
}

export async function listSessions(): Promise<SessionSummary[]> {
  const payload = await request<{ sessions: SessionSummary[] }>("/api/sessions");
  return payload.sessions;
}

export async function createSession(title?: string): Promise<SessionSummary> {
  const payload = await request<{ session: SessionSummary }>("/api/sessions", {
    method: "POST",
    body: JSON.stringify(title ? { title } : {}),
  });
  return payload.session;
}

export async function deleteSession(sessionId: string): Promise<void> {
  await request<{ deleted: boolean }>(`/api/sessions/${sessionId}`, {
    method: "DELETE",
  });
}

export async function getSession(sessionId: string): Promise<SessionPayload> {
  return request<SessionPayload>(`/api/sessions/${sessionId}`);
}

export async function createRun(sessionId: string, prompt: string): Promise<{ run_id: string; status: string }> {
  return request<{ run_id: string; status: string }>(`/api/sessions/${sessionId}/runs`, {
    method: "POST",
    body: JSON.stringify({ prompt }),
  });
}

export type SessionSummary = {
  id: string;
  title: string;
  status: string;
  created_at: string;
  updated_at: string;
  last_message_preview: string | null;
  latest_run_id: string | null;
  latest_run_status: string | null;
  run_count: number;
};

export type SessionRecord = {
  id: string;
  title: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type MessageRecord = {
  id: string;
  session_id: string;
  role: string;
  content: string;
  created_at: string;
  run_id: string | null;
};

export type RunRecord = {
  id: string;
  session_id: string;
  prompt: string;
  status: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  exit_code: number | null;
  output: string;
  error: string | null;
};

export type SessionPayload = {
  session: SessionRecord;
  messages: MessageRecord[];
  runs: RunRecord[];
};

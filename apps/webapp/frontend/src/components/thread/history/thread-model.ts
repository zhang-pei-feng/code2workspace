import { Thread } from "@langchain/langgraph-sdk";

const THREAD_MODEL_METADATA_KEY = "epimindagent_model_spec";
const LEGACY_THREAD_MODEL_METADATA_KEY = "code2workspace_model_spec";

export function getThreadModelSpec(thread: Thread | null | undefined): string | null {
  if (!thread?.metadata || typeof thread.metadata !== "object") {
    return null;
  }
  const metadata = thread.metadata as Record<string, unknown>;
  const raw =
    metadata[THREAD_MODEL_METADATA_KEY] ?? metadata[LEGACY_THREAD_MODEL_METADATA_KEY];
  if (typeof raw !== "string") {
    return null;
  }
  const model = raw.trim();
  return model.length > 0 ? model : null;
}

export function buildThreadMetadataWithModel(
  metadata: Record<string, unknown> | null | undefined,
  model: string | null,
): Record<string, unknown> {
  const next = { ...(metadata ?? {}) };
  if (!model) {
    delete next[THREAD_MODEL_METADATA_KEY];
    delete next[LEGACY_THREAD_MODEL_METADATA_KEY];
    return next;
  }
  delete next[LEGACY_THREAD_MODEL_METADATA_KEY];
  next[THREAD_MODEL_METADATA_KEY] = model.trim();
  return next;
}

import { type Message } from "@langchain/langgraph-sdk";

type MessageLike = Message & { id?: string | null };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isMessageLike(value: unknown): value is MessageLike {
  return isRecord(value) && typeof value.type === "string";
}

function getUpdateMessages(value: unknown): MessageLike[] {
  if (Array.isArray(value)) {
    return value.filter(isMessageLike);
  }
  if (isRecord(value) && Array.isArray(value.value)) {
    return value.value.filter(isMessageLike);
  }
  return [];
}

export function extractMessagesFromUpdateEvent(data: unknown): MessageLike[] {
  if (!isRecord(data)) return [];
  const messages: MessageLike[] = [];
  for (const nodeData of Object.values(data)) {
    if (!isRecord(nodeData) || !("messages" in nodeData)) continue;
    messages.push(...getUpdateMessages(nodeData.messages));
  }
  return messages;
}

export function mergeMessagesById(
  current: MessageLike[] | undefined,
  incoming: MessageLike[],
): MessageLike[] {
  const merged = [...(current ?? [])];
  for (const message of incoming) {
    if (!message.id) {
      merged.push(message);
      continue;
    }
    const index = merged.findIndex((item) => item.id === message.id);
    if (index >= 0) {
      const previous = merged[index];
      const next = { ...previous, ...message };
      if (
        "tool_calls" in previous &&
        Array.isArray((previous as Record<string, unknown>).tool_calls) &&
        (!("tool_calls" in message) ||
          !Array.isArray((message as Record<string, unknown>).tool_calls))
      ) {
        (next as Record<string, unknown>).tool_calls =
          (previous as Record<string, unknown>).tool_calls;
      }
      if (
        "invalid_tool_calls" in previous &&
        Array.isArray((previous as Record<string, unknown>).invalid_tool_calls) &&
        (!("invalid_tool_calls" in message) ||
          !Array.isArray((message as Record<string, unknown>).invalid_tool_calls))
      ) {
        (next as Record<string, unknown>).invalid_tool_calls =
          (previous as Record<string, unknown>).invalid_tool_calls;
      }
      merged[index] = next;
      continue;
    }
    merged.push(message);
  }
  return merged;
}

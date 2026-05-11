import { Message } from "@langchain/langgraph-sdk";

const THREAD_STREAM_MODES = ["messages", "updates", "values"] as const;

export function buildThreadStreamSubmitOptions<T extends Record<string, unknown>>(
  overrides: T,
) {
  return {
    ...overrides,
    streamMode: [...THREAD_STREAM_MODES],
    streamSubgraphs: true as const,
    streamResumable: true as const,
  };
}

export function isAssistantActivityMessage(
  message: Pick<Message, "type"> | undefined | null,
): boolean {
  return message?.type === "ai" || message?.type === "tool";
}

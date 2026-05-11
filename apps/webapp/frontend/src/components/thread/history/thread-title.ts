import { Thread } from "@langchain/langgraph-sdk";

import { getContentString } from "../utils";

export function getThreadDisplayTitle(thread: Thread): string {
  const metadataTitle =
    typeof thread.metadata === "object" &&
    thread.metadata &&
    typeof thread.metadata.title === "string"
      ? thread.metadata.title.trim()
      : "";
  if (metadataTitle) {
    return metadataTitle;
  }

  if (
    typeof thread.values === "object" &&
    thread.values &&
    "messages" in thread.values &&
    Array.isArray(thread.values.messages) &&
    thread.values.messages.length > 0
  ) {
    const firstMessage = thread.values.messages[0];
    const content = getContentString(firstMessage.content);
    if (content.trim()) {
      return content;
    }
  }

  return thread.thread_id;
}

export function buildRenamedThreadMetadata(
  metadata: Thread["metadata"],
  title: string,
): Record<string, unknown> {
  return {
    ...(typeof metadata === "object" && metadata ? metadata : {}),
    title: title.trim(),
  };
}

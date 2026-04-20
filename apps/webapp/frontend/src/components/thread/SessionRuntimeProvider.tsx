import {
  AssistantRuntimeProvider,
  useExternalStoreRuntime,
  type AppendMessage,
  type ThreadMessageLike,
} from "@assistant-ui/react";
import { useEffect, useMemo, useState, type PropsWithChildren } from "react";

import type { MessageRecord } from "@/types";

function toThreadMessage(message: MessageRecord): ThreadMessageLike {
  return {
    id: message.id,
    role: message.role === "assistant" ? "assistant" : "user",
    content: [{ type: "text", text: message.content }],
  };
}

type SessionRuntimeProviderProps = PropsWithChildren<{
  sessionId: string | null;
  messages: MessageRecord[];
  isRunning: boolean;
  onSubmit: (prompt: string) => Promise<void>;
}>;

export function SessionRuntimeProvider({
  children,
  sessionId,
  messages: serverMessages,
  isRunning,
  onSubmit,
}: SessionRuntimeProviderProps) {
  const mappedMessages = useMemo(
    () => serverMessages.map(toThreadMessage),
    [serverMessages],
  );
  const [messages, setMessages] = useState<readonly ThreadMessageLike[]>(mappedMessages);

  useEffect(() => {
    setMessages(mappedMessages);
  }, [mappedMessages, sessionId]);

  const runtime = useExternalStoreRuntime<ThreadMessageLike>({
    messages,
    setMessages,
    isRunning,
    convertMessage: (message) => message,
    onNew: async (message: AppendMessage) => {
      const textPart = message.content.find((part) => part.type === "text");
      if (!textPart || textPart.type !== "text") {
        throw new Error("Only plain text input is supported");
      }

      const optimisticMessage: ThreadMessageLike = {
        id: `optimistic-${Date.now()}`,
        role: "user",
        content: [{ type: "text", text: textPart.text }],
      };
      setMessages((current) => [...current, optimisticMessage]);
      try {
        await onSubmit(textPart.text);
      } catch (error) {
        setMessages(mappedMessages);
        throw error;
      }
    },
  });

  return <AssistantRuntimeProvider runtime={runtime}>{children}</AssistantRuntimeProvider>;
}

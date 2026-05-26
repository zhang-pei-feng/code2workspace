import { v4 as uuidv4 } from "uuid";
import { ReactNode, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { useSearchParams } from "next/navigation";
import { cn } from "@/lib/utils";
import { buildSettingsHref } from "@/lib/settings";
import { useStreamContext } from "@/providers/Stream";
import { FormEvent } from "react";
import { Button } from "../ui/button";
import { Checkpoint, Message } from "@langchain/langgraph-sdk";
import {
  AssistantMessage,
  AssistantMessageLoading,
  isBreakpointInterrupt,
} from "./messages/ai";
import { HumanMessage } from "./messages/human";
import {
  DO_NOT_RENDER_ID_PREFIX,
  ensureToolCallsHaveResponses,
} from "@/lib/ensure-tool-responses";
import {
  ArrowDown,
  CircleAlert,
  Files,
  PanelRightOpen,
  PanelRightClose,
  LoaderCircle,
  XIcon,
  Plus,
} from "lucide-react";
import { useQueryState, parseAsBoolean } from "nuqs";
import { StickToBottom, useStickToBottomContext } from "use-stick-to-bottom";
import ThreadHistory from "./history";
import { toast } from "sonner";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { Label } from "../ui/label";
import { Switch } from "../ui/switch";
import { useFileUpload } from "@/hooks/use-file-upload";
import { ContentBlocksPreview } from "./ContentBlocksPreview";
import {
  useArtifactOpen,
  ArtifactContent,
  ArtifactTitle,
  useArtifactContext,
} from "./artifact";
import {
  buildThreadStreamSubmitOptions,
  isAssistantActivityMessage,
} from "./streaming";
import { ThreadHeaderActions } from "./header-actions";
import { useThreads } from "@/providers/Thread";
import { getThreadModelSpec } from "./history/thread-model";
import { ModelOption, ModelSelector } from "./model-selector";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "../ui/sheet";
import { WorkspacePanel } from "./workspace-panel";
import {
  downloadWorkspacePath,
  fetchWorkspaceFile,
  getWorkspacePreviewKind,
  type WorkspaceEntry,
  type WorkspacePreviewKind,
} from "@/lib/workspace";

function StickyToBottomContent(props: {
  content: ReactNode;
  footer?: ReactNode;
  className?: string;
  contentClassName?: string;
}) {
  const context = useStickToBottomContext();
  return (
    <div
      ref={context.scrollRef}
      style={{ width: "100%", height: "100%" }}
      className={props.className}
    >
      <div
        ref={context.contentRef}
        className={props.contentClassName}
      >
        {props.content}
      </div>

      {props.footer}
    </div>
  );
}

type PendingSubmission = {
  messages: Message[];
  context?: Record<string, unknown>;
};

type PreviewTab = {
  path: string;
  name: string;
  kind: WorkspacePreviewKind;
  status: "loading" | "ready" | "unsupported" | "error";
  content?: string;
  truncated?: boolean;
  objectUrl?: string;
  message?: string;
};

function ScrollToBottom(props: { className?: string }) {
  const { isAtBottom, scrollToBottom } = useStickToBottomContext();

  if (isAtBottom) return null;
  return (
    <Button
      variant="outline"
      className={props.className}
      onClick={() => scrollToBottom()}
    >
      <ArrowDown className="h-4 w-4" />
      <span>Scroll to bottom</span>
    </Button>
  );
}

export function Thread() {
  const [artifactContext, setArtifactContext] = useArtifactContext();
  const [artifactOpen, closeArtifact] = useArtifactOpen();
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const searchParams = useSearchParams();

  const [threadId, _setThreadId] = useQueryState("threadId");
  const [chatHistoryOpen, setChatHistoryOpen] = useQueryState(
    "chatHistoryOpen",
    parseAsBoolean.withDefault(false),
  );
  const [hideToolCalls, setHideToolCalls] = useQueryState(
    "hideToolCalls",
    parseAsBoolean.withDefault(false),
  );
  const [input, setInput] = useState("");
  const {
    contentBlocks,
    setContentBlocks,
    handleFileUpload,
    dropRef,
    removeBlock,
    resetBlocks: _resetBlocks,
    dragOver,
    handlePaste,
  } = useFileUpload();
  const [firstTokenReceived, setFirstTokenReceived] = useState(false);
  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  const [draftThreadModel, setDraftThreadModel] = useState<string | null>(null);
  const [availableModels, setAvailableModels] = useState<ModelOption[]>([]);
  const [defaultModel, setDefaultModel] = useState<string | null>(null);
  const [pendingSubmission, setPendingSubmission] =
    useState<PendingSubmission | null>(null);
  const [previewTabs, setPreviewTabs] = useState<PreviewTab[]>([]);
  const [activeMainTab, setActiveMainTab] = useState<string>("chat");
  const isLargeScreen = useMediaQuery("(min-width: 1024px)");
  const { threads, setThreadModel, createThread } = useThreads();

  const stream = useStreamContext();
  const messages = stream.messages;
  const isLoading = stream.isLoading;
  const activeThread = threadId
    ? threads.find((thread) => thread.thread_id === threadId) ?? null
    : null;
  const activeThreadModel = getThreadModelSpec(activeThread);
  const selectedThreadModel = activeThreadModel ?? draftThreadModel;
  const settingsHref = buildSettingsHref(searchParams.toString());

  const lastError = useRef<string | undefined>(undefined);

  const revokePreviewObjectUrl = (tab: PreviewTab | undefined) => {
    if (tab?.objectUrl) {
      URL.revokeObjectURL(tab.objectUrl);
    }
  };

  const setThreadId = (id: string | null) => {
    _setThreadId(id);
    if (id === null) {
      setDraftThreadModel(null);
    }

    // close artifact and reset artifact context
    closeArtifact();
    setArtifactContext({});
    setPreviewTabs((current) => {
      current.forEach(revokePreviewObjectUrl);
      return [];
    });
    setActiveMainTab("chat");
  };

  const upsertPreviewTab = (path: string, nextTab: PreviewTab) => {
    setPreviewTabs((current) => {
      const index = current.findIndex((tab) => tab.path === path);
      if (index === -1) {
        return [...current, nextTab];
      }
      const previous = current[index];
      if (previous.objectUrl && previous.objectUrl !== nextTab.objectUrl) {
        URL.revokeObjectURL(previous.objectUrl);
      }
      const next = [...current];
      next[index] = nextTab;
      return next;
    });
  };

  const closePreviewTab = (path: string) => {
    setPreviewTabs((current) => {
      const closingTab = current.find((tab) => tab.path === path);
      revokePreviewObjectUrl(closingTab);
      const remaining = current.filter((tab) => tab.path !== path);
      setActiveMainTab((active) => {
        if (active !== path) {
          return active;
        }
        return remaining.length > 0 ? remaining[remaining.length - 1].path : "chat";
      });
      return remaining;
    });
  };

  const openWorkspacePreview = async (entry: WorkspaceEntry) => {
    if (!threadId || entry.type !== "file") {
      return;
    }
    const previewKind = getWorkspacePreviewKind(entry);
    setActiveMainTab(entry.path);
    const existing = previewTabs.find((tab) => tab.path === entry.path);
    if (existing && existing.status === "ready" && existing.kind === previewKind) {
      return;
    }
    if (previewKind === "unsupported") {
      upsertPreviewTab(entry.path, {
        path: entry.path,
        name: entry.name,
        kind: previewKind,
        status: "unsupported",
        message: "Preview is not supported for this file type or file size.",
      });
      return;
    }
    upsertPreviewTab(entry.path, {
      path: entry.path,
      name: entry.name,
      kind: previewKind,
      status: "loading",
    });
    try {
      if (previewKind === "image" || previewKind === "pdf") {
        const { blob } = await downloadWorkspacePath(threadId, entry.path);
        const objectUrl = URL.createObjectURL(blob);
        upsertPreviewTab(entry.path, {
          path: entry.path,
          name: entry.name,
          kind: previewKind,
          status: "ready",
          objectUrl,
        });
        return;
      }
      const response = await fetchWorkspaceFile(threadId, entry.path);
      upsertPreviewTab(entry.path, {
        path: entry.path,
        name: entry.name,
        kind: previewKind,
        status: "ready",
        content: response.content,
        truncated: response.truncated,
      });
    } catch (err) {
      upsertPreviewTab(entry.path, {
        path: entry.path,
        name: entry.name,
        kind: previewKind,
        status: "error",
        message:
          err instanceof Error
            ? err.message
            : "Failed to load workspace preview.",
      });
    }
  };

  const activePreviewTab =
    previewTabs.find((tab) => tab.path === activeMainTab) ?? null;

  useEffect(() => {
    let cancelled = false;
    fetch("/api/models")
      .then(async (response) => {
        if (!response.ok) {
          throw new Error("Failed to load models.");
        }
        return response.json();
      })
      .then((payload) => {
        if (cancelled) return;
        setAvailableModels(payload.models ?? []);
        setDefaultModel(payload.default_model ?? null);
      })
      .catch(console.error);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    setPreviewTabs((current) => {
      current.forEach(revokePreviewObjectUrl);
      return [];
    });
    setActiveMainTab("chat");
  }, [threadId]);

  useEffect(() => {
    if (!threadId || !activeThread || !draftThreadModel || activeThreadModel) {
      return;
    }
    void setThreadModel(activeThread, draftThreadModel)
      .then(() => setDraftThreadModel(null))
      .catch(console.error);
  }, [threadId, activeThread, activeThreadModel, draftThreadModel, setThreadModel]);

  useEffect(() => {
    if (!threadId || !pendingSubmission) {
      return;
    }
    const context = pendingSubmission.context;
    stream.submit(
      {
        messages: pendingSubmission.messages,
      },
      buildThreadStreamSubmitOptions({
        context,
        optimisticValues: (
          prev: Record<string, unknown> & { messages?: Message[] },
        ) => ({
          ...prev,
          context,
          messages: [...(prev.messages ?? []), ...pendingSubmission.messages],
        }),
      }),
    );
    setPendingSubmission(null);
  }, [threadId, pendingSubmission, stream]);

  useEffect(() => {
    if (!stream.error) {
      lastError.current = undefined;
      return;
    }
    try {
      const message = (stream.error as any).message;
      if (!message || lastError.current === message) {
        // Message has already been logged. do not modify ref, return early.
        return;
      }

      // Message is defined, and it has not been logged yet. Save it, and send the error
      lastError.current = message;
      toast.error("An error occurred. Please try again.", {
        description: (
          <p>
            <strong>Error:</strong> <code>{message}</code>
          </p>
        ),
        richColors: true,
        closeButton: true,
      });
    } catch {
      // no-op
    }
  }, [stream.error]);

  // TODO: this should be part of the useStream hook
  const prevMessageLength = useRef(0);
  useEffect(() => {
    const lastMessage = messages[messages.length - 1];
    if (
      messages.length !== prevMessageLength.current &&
      isAssistantActivityMessage(lastMessage)
    ) {
      setFirstTokenReceived(true);
    }

    prevMessageLength.current = messages.length;
  }, [messages]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if ((input.trim().length === 0 && contentBlocks.length === 0) || isLoading)
      return;
    setFirstTokenReceived(false);

    const newHumanMessage: Message = {
      id: uuidv4(),
      type: "human",
      content: [
        ...(input.trim().length > 0 ? [{ type: "text", text: input }] : []),
        ...contentBlocks,
      ] as Message["content"],
    };

    const toolMessages = ensureToolCallsHaveResponses(stream.messages);

    const context =
      Object.keys(artifactContext).length > 0 ? { ...artifactContext } : {};
    if (selectedThreadModel) {
      context.model = selectedThreadModel;
    }

    const nextMessages = [...toolMessages, newHumanMessage];
    const nextContext = Object.keys(context).length > 0 ? context : undefined;
    setInput("");
    setContentBlocks([]);
    setModelMenuOpen(false);

    if (!threadId) {
      const createdThread = await createThread();
      setPendingSubmission({
        messages: nextMessages,
        context: nextContext,
      });
      setThreadId(createdThread.thread_id);
      return;
    }

    stream.submit(
      {
        messages: nextMessages,
      },
      buildThreadStreamSubmitOptions({
        context: nextContext,
        optimisticValues: (
          prev: Record<string, unknown> & { messages?: Message[] },
        ) => ({
          ...prev,
          context: nextContext,
          messages: [...(prev.messages ?? []), ...nextMessages],
        }),
      }),
    );
  };

  const handleRegenerate = (
    parentCheckpoint: Checkpoint | null | undefined,
  ) => {
    // Do this so the loading state is correct
    prevMessageLength.current = prevMessageLength.current - 1;
    setFirstTokenReceived(false);
    stream.submit(
      undefined,
      buildThreadStreamSubmitOptions({
        checkpoint: parentCheckpoint,
      }),
    );
  };

  const chatStarted = !!threadId || !!messages.length;
  const hasNoAIOrToolMessages = !messages.find(
    (m) => m.type === "ai" || m.type === "tool",
  );
  const showingChatTab = activeMainTab === "chat" || activePreviewTab === null;

  return (
    <div className="flex h-screen w-full overflow-hidden">
      <div className="relative hidden lg:flex">
        <motion.div
          className="absolute z-20 h-full overflow-hidden border-r bg-background"
          style={{ width: 300 }}
          animate={
            isLargeScreen
              ? { x: chatHistoryOpen ? 0 : -300 }
              : { x: chatHistoryOpen ? 0 : -300 }
          }
          initial={{ x: -300 }}
          transition={
            isLargeScreen
              ? { type: "spring", stiffness: 300, damping: 30 }
              : { duration: 0 }
          }
        >
          <div
            className="relative h-full"
            style={{ width: 300 }}
          >
            <ThreadHistory />
          </div>
        </motion.div>
      </div>

      <div className="flex w-full min-w-0">
        <motion.div
          className={cn(
            "relative flex min-w-0 flex-1 flex-col overflow-hidden",
            !chatStarted && "grid-rows-[1fr]",
          )}
          layout={isLargeScreen}
          animate={{
            marginLeft: chatHistoryOpen ? (isLargeScreen ? 300 : 0) : 0,
            width: chatHistoryOpen
              ? isLargeScreen
                ? "calc(100% - 300px)"
                : "100%"
              : "100%",
          }}
          transition={
            isLargeScreen
              ? { type: "spring", stiffness: 300, damping: 30 }
              : { duration: 0 }
          }
        >
          {!chatStarted && (
            <div className="absolute top-0 left-0 z-10 flex w-full items-center justify-between gap-3 p-2 pl-4">
              <div>
                {(!chatHistoryOpen || !isLargeScreen) && (
                  <Button
                    className="hover:bg-accent"
                    variant="ghost"
                    onClick={() => setChatHistoryOpen((p) => !p)}
                  >
                    {chatHistoryOpen ? (
                      <PanelRightOpen className="size-5" />
                    ) : (
                      <PanelRightClose className="size-5" />
                    )}
                  </Button>
                )}
              </div>
              <div className="pr-2">
                <div className="flex items-center gap-2">
                  {!isLargeScreen && (
                    <Button
                      variant="ghost"
                      className="gap-2 px-3"
                      onClick={() => setWorkspaceOpen(true)}
                    >
                      <Files className="size-5" />
                      文件
                    </Button>
                  )}
                  <ThreadHeaderActions
                    settingsHref={settingsHref}
                    onNewThread={() => setThreadId(null)}
                  />
                </div>
              </div>
            </div>
          )}
          {chatStarted && (
            <div className="relative z-10 flex items-center justify-between gap-3 p-2">
              <div className="relative flex items-center justify-start gap-2">
                <div className="absolute left-0 z-10">
                  {(!chatHistoryOpen || !isLargeScreen) && (
                    <Button
                    className="hover:bg-accent"
                      variant="ghost"
                      onClick={() => setChatHistoryOpen((p) => !p)}
                    >
                      {chatHistoryOpen ? (
                        <PanelRightOpen className="size-5" />
                      ) : (
                        <PanelRightClose className="size-5" />
                      )}
                    </Button>
                  )}
                </div>
                <motion.button
                  className="flex cursor-pointer items-center gap-2"
                  onClick={() => setThreadId(null)}
                  animate={{
                    marginLeft: !chatHistoryOpen ? 48 : 0,
                  }}
                  transition={{
                    type: "spring",
                    stiffness: 300,
                    damping: 30,
                  }}
                >
                  <span className="text-xl font-semibold tracking-tight">
                    EpiMindAgent Chat
                  </span>
                </motion.button>
              </div>

              <div className="flex items-center gap-4">
                {!isLargeScreen && (
                  <Button
                    variant="ghost"
                    className="gap-2 px-3"
                    onClick={() => setWorkspaceOpen(true)}
                  >
                    <Files className="size-5" />
                    文件
                  </Button>
                )}
                <ThreadHeaderActions
                  settingsHref={settingsHref}
                  onNewThread={() => setThreadId(null)}
                />
              </div>

              <div className="from-background to-background/0 absolute inset-x-0 top-full h-5 bg-gradient-to-b" />
            </div>
          )}

          {previewTabs.length > 0 && (
            <div className="border-b border-slate-200 bg-background px-2 py-2">
              <div className="flex items-center gap-2 overflow-x-auto">
                <button
                  type="button"
                  className={cn(
                    "shrink-0 rounded-md px-3 py-1.5 text-sm",
                    showingChatTab
                      ? "bg-slate-200 text-slate-950"
                      : "bg-slate-100 text-slate-600",
                  )}
                  onClick={() => setActiveMainTab("chat")}
                >
                  对话
                </button>
                {previewTabs.map((tab) => {
                  const active = tab.path === activeMainTab;
                  return (
                    <div
                      key={tab.path}
                      className={cn(
                        "flex min-w-0 shrink-0 items-center gap-1 rounded-md px-2 py-1.5 text-sm",
                        active
                          ? "bg-slate-200 text-slate-950"
                          : "bg-slate-100 text-slate-600",
                      )}
                    >
                      <button
                        type="button"
                        className="max-w-[220px] truncate"
                        onClick={() => setActiveMainTab(tab.path)}
                      >
                        {tab.name}
                      </button>
                      <button
                        type="button"
                        className="text-slate-500 hover:text-slate-900"
                        onClick={() => closePreviewTab(tab.path)}
                      >
                        <XIcon className="size-3.5" />
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {showingChatTab ? (
            <StickToBottom className="relative flex-1 overflow-hidden">
              <StickyToBottomContent
                className={cn(
                  "absolute inset-0 overflow-y-scroll px-4 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-gray-300 [&::-webkit-scrollbar-track]:bg-transparent",
                  !chatStarted && "mt-[25vh] flex flex-col items-stretch",
                  chatStarted && "grid grid-rows-[1fr_auto]",
                )}
                contentClassName="pt-8 pb-16 max-w-3xl mx-auto flex flex-col gap-4 w-full"
                content={
                  <>
                    {messages
                      .filter((m) => !m.id?.startsWith(DO_NOT_RENDER_ID_PREFIX))
                      .map((message, index) =>
                        message.type === "human" ? (
                          <HumanMessage
                            key={message.id || `${message.type}-${index}`}
                            message={message}
                            isLoading={isLoading}
                          />
                        ) : (
                          <AssistantMessage
                            key={message.id || `${message.type}-${index}`}
                            message={message}
                            isLoading={isLoading}
                            handleRegenerate={handleRegenerate}
                          />
                        ),
                      )}
                    {hasNoAIOrToolMessages && !!stream.interrupt && (
                      isBreakpointInterrupt(stream.interrupt) ? (
                        <AssistantMessageLoading key="breakpoint-loading" />
                      ) : (
                        <AssistantMessage
                          key="interrupt-msg"
                          message={undefined}
                          isLoading={isLoading}
                          handleRegenerate={handleRegenerate}
                        />
                      )
                    )}
                    {isLoading && !firstTokenReceived && (
                      <AssistantMessageLoading />
                    )}
                  </>
                }
                footer={
                  <div className="sticky bottom-0 flex flex-col items-center gap-8 bg-background">
                    {!chatStarted && (
                      <div className="flex items-center">
                        <h1 className="text-2xl font-semibold tracking-tight">
                          EpiMindAgent Chat
                        </h1>
                      </div>
                    )}

                    <ScrollToBottom className="animate-in fade-in-0 zoom-in-95 absolute bottom-full left-1/2 mb-4 -translate-x-1/2" />

                    <div
                      ref={dropRef}
                      className={cn(
                        "bg-muted relative z-10 mx-auto mb-8 w-full max-w-3xl rounded-2xl shadow-xs transition-all",
                        dragOver
                          ? "border-primary border-2 border-dotted"
                          : "border border-solid",
                      )}
                    >
                      <form
                        onSubmit={handleSubmit}
                        className="mx-auto grid max-w-3xl grid-rows-[1fr_auto] gap-2"
                      >
                        <ContentBlocksPreview
                          blocks={contentBlocks}
                          onRemove={removeBlock}
                        />
                        <textarea
                          value={input}
                          onChange={(e) => setInput(e.target.value)}
                          onPaste={handlePaste}
                          onKeyDown={(e) => {
                            if (
                              e.key === "Enter" &&
                              !e.shiftKey &&
                              !e.metaKey &&
                              !e.nativeEvent.isComposing
                            ) {
                              e.preventDefault();
                              const el = e.target as HTMLElement | undefined;
                              const form = el?.closest("form");
                              form?.requestSubmit();
                            }
                          }}
                          placeholder="Type your message..."
                          className="field-sizing-content resize-none border-none bg-transparent p-3.5 pb-0 shadow-none ring-0 outline-none focus:ring-0 focus:outline-none"
                        />

                        <div className="flex items-center gap-6 p-2 pt-4">
                          <div>
                            <div className="flex items-center space-x-2">
                              <Switch
                                id="render-tool-calls"
                                checked={hideToolCalls ?? false}
                                onCheckedChange={setHideToolCalls}
                              />
                              <Label
                                htmlFor="render-tool-calls"
                                className="text-sm text-muted-foreground"
                              >
                                Hide Tool Calls
                              </Label>
                            </div>
                          </div>
                          <Label
                            htmlFor="file-input"
                            className="flex cursor-pointer items-center gap-2"
                          >
                            <Plus className="size-5 text-muted-foreground" />
                            <span className="text-sm text-muted-foreground">
                              Upload PDF or Image
                            </span>
                          </Label>
                          <input
                            id="file-input"
                            type="file"
                            onChange={handleFileUpload}
                            multiple
                            accept="image/jpeg,image/png,image/gif,image/webp,application/pdf"
                            className="hidden"
                          />
                          <ModelSelector
                            currentModel={selectedThreadModel}
                            defaultModel={defaultModel}
                            models={availableModels}
                            open={modelMenuOpen}
                            disabled={isLoading || availableModels.length === 0}
                            onToggle={() => setModelMenuOpen((current) => !current)}
                            onSelect={(model) => {
                              setModelMenuOpen(false);
                              if (activeThread) {
                                void setThreadModel(activeThread, model).catch(console.error);
                                return;
                              }
                              setDraftThreadModel(model);
                            }}
                          />
                          {stream.isLoading ? (
                            <Button
                              key="stop"
                              onClick={() => stream.stop()}
                              className="ml-auto"
                            >
                              <LoaderCircle className="h-4 w-4 animate-spin" />
                              Cancel
                            </Button>
                          ) : (
                            <Button
                              type="submit"
                              className="ml-auto shadow-md transition-all"
                              disabled={
                                isLoading ||
                                (!input.trim() && contentBlocks.length === 0)
                              }
                            >
                              Send
                            </Button>
                          )}
                        </div>
                      </form>
                    </div>
                  </div>
                }
              />
            </StickToBottom>
          ) : (
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-background">
              <div className="min-h-0 flex-1 overflow-auto p-6">
                {activePreviewTab?.status === "loading" && (
                  <div className="flex items-center gap-2 text-sm text-slate-500">
                    <LoaderCircle className="size-4 animate-spin" />
                    Loading preview…
                  </div>
                )}
                {activePreviewTab?.status === "unsupported" && (
                  <div className="mx-auto max-w-3xl rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
                    <div className="flex items-start gap-2">
                      <CircleAlert className="mt-0.5 size-4" />
                      <span>{activePreviewTab.message}</span>
                    </div>
                  </div>
                )}
                {activePreviewTab?.status === "error" && (
                  <div className="mx-auto max-w-3xl rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
                    <div className="flex items-start gap-2">
                      <CircleAlert className="mt-0.5 size-4" />
                      <span>{activePreviewTab.message}</span>
                    </div>
                  </div>
                )}
                {activePreviewTab?.status === "ready" &&
                  activePreviewTab.kind === "image" &&
                  activePreviewTab.objectUrl && (
                    <div className="flex h-full items-center justify-center">
                      <img
                        src={activePreviewTab.objectUrl}
                        alt={`${activePreviewTab.name} preview`}
                        className="max-h-full max-w-full rounded-lg border border-slate-200 object-contain"
                      />
                    </div>
                  )}
                {activePreviewTab?.status === "ready" &&
                  activePreviewTab.kind === "pdf" &&
                  activePreviewTab.objectUrl && (
                    <iframe
                      src={activePreviewTab.objectUrl}
                      title={`${activePreviewTab.name} preview`}
                      className="h-full min-h-[70vh] w-full rounded-lg border border-slate-200"
                    />
                  )}
                {activePreviewTab?.status === "ready" &&
                  (activePreviewTab.kind === "text" ||
                    activePreviewTab.kind === "docx") && (
                    <div className="mx-auto max-w-5xl space-y-3">
                      {activePreviewTab.truncated && (
                        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                          Preview truncated for this file.
                        </div>
                      )}
                      <pre className="whitespace-pre-wrap break-words rounded-lg bg-slate-950 p-4 text-sm text-slate-100">
                        {activePreviewTab.content}
                      </pre>
                    </div>
                  )}
              </div>
            </div>
          )}
        </motion.div>
        <div className="hidden w-[400px] min-w-[400px] border-l bg-background lg:flex lg:flex-col xl:w-[440px] xl:min-w-[440px]">
          <div
            className={cn(
              "grid min-h-0 flex-1",
              artifactOpen
                ? "grid-rows-[minmax(0,1fr)_minmax(0,1fr)]"
                : "grid-rows-[minmax(0,1fr)]",
            )}
          >
            <WorkspacePanel threadId={threadId} onOpenPreview={openWorkspacePreview} />
            {artifactOpen && (
              <div className="flex min-h-0 flex-col border-t bg-background">
                <div className="grid grid-cols-[1fr_auto] border-b p-4">
                  <ArtifactTitle className="truncate overflow-hidden" />
                  <button
                    onClick={closeArtifact}
                    className="cursor-pointer"
                  >
                    <XIcon className="size-5" />
                  </button>
                </div>
                <ArtifactContent className="relative min-h-0 flex-1" />
              </div>
            )}
          </div>
        </div>
      </div>
      <Sheet
        open={workspaceOpen}
        onOpenChange={setWorkspaceOpen}
      >
        <SheetContent
          side="right"
          className="w-full p-0 sm:max-w-md"
        >
          <SheetHeader className="sr-only">
            <SheetTitle>Workspace</SheetTitle>
            <SheetDescription>Current thread workspace tree.</SheetDescription>
          </SheetHeader>
          <WorkspacePanel
            threadId={threadId}
            className="h-full"
            onOpenPreview={openWorkspacePreview}
          />
        </SheetContent>
      </Sheet>
    </div>
  );
}

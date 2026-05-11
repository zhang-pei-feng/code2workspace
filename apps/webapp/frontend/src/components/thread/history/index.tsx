import { Button } from "@/components/ui/button";
import { useThreads } from "@/providers/Thread";
import { Thread } from "@langchain/langgraph-sdk";
import { useCallback, useEffect, useRef, useState } from "react";

import { useQueryState, parseAsBoolean } from "nuqs";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import {
  ChevronLeft,
  ChevronRight,
  Check,
  Ellipsis,
  PanelRightOpen,
  PanelRightClose,
  Pencil,
  SquarePen,
  Trash2,
  X,
} from "lucide-react";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { getThreadDisplayTitle } from "./thread-title";

function ThreadList({
  threads,
  onRenameThread,
  onDeleteThread,
  onThreadClick,
}: {
  threads: Thread[];
  onRenameThread: (thread: Thread, title: string) => Promise<void>;
  onDeleteThread: (thread: Thread) => Promise<void>;
  onThreadClick?: (threadId: string) => void;
}) {
  const [threadId, setThreadId] = useQueryState("threadId");
  const [editingThreadId, setEditingThreadId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [savingThreadId, setSavingThreadId] = useState<string | null>(null);
  const [deletingThreadId, setDeletingThreadId] = useState<string | null>(null);
  const [openMenuThreadId, setOpenMenuThreadId] = useState<string | null>(null);

  return (
    <div className="flex h-full w-full flex-col items-start justify-start gap-2 overflow-y-scroll [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-gray-300 [&::-webkit-scrollbar-track]:bg-transparent">
      {threads.map((t) => {
        const itemText = getThreadDisplayTitle(t);
        const isEditing = editingThreadId === t.thread_id;
        const isSaving = savingThreadId === t.thread_id;
        const isDeleting = deletingThreadId === t.thread_id;
        const isMenuOpen = openMenuThreadId === t.thread_id;

        const startEditing = () => {
          setEditingThreadId(t.thread_id);
          setDraftTitle(itemText);
          setOpenMenuThreadId(null);
        };

        const cancelEditing = () => {
          setEditingThreadId(null);
          setDraftTitle("");
        };

        const saveEditing = async () => {
          const title = draftTitle.trim();
          if (!title || isSaving) return;
          setSavingThreadId(t.thread_id);
          try {
            await onRenameThread(t, title);
            cancelEditing();
          } catch (error) {
            console.error(error);
          } finally {
            setSavingThreadId(null);
          }
        };

        const deleteCurrentThread = async () => {
          if (isDeleting) return;
          setDeletingThreadId(t.thread_id);
          try {
            await onDeleteThread(t);
            if (t.thread_id === threadId) {
              setThreadId(null);
            }
          } catch (error) {
            console.error(error);
          } finally {
            setDeletingThreadId(null);
            setOpenMenuThreadId(null);
          }
        };

        return (
          <div
            key={t.thread_id}
            className="w-full px-1"
          >
            <div
              data-thread-row={t.thread_id}
              className={
                isEditing
                  ? "flex w-full max-w-[280px] items-center gap-2"
                  : "group relative grid w-full max-w-[280px] grid-cols-[minmax(0,1fr)_auto] items-center gap-2"
              }
            >
              {isEditing ? (
                <>
                  <Input
                    value={draftTitle}
                    autoFocus
                    className="h-8"
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => setDraftTitle(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        void saveEditing();
                      }
                      if (e.key === "Escape") {
                        e.preventDefault();
                        cancelEditing();
                      }
                    }}
                  />
                  <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    className="size-8 shrink-0"
                    aria-label="Save thread title"
                    disabled={!draftTitle.trim() || isSaving}
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      void saveEditing();
                    }}
                  >
                    <Check className="size-4" />
                  </Button>
                  <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    className="size-8 shrink-0"
                    aria-label="Cancel thread title edit"
                    disabled={isSaving}
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      cancelEditing();
                    }}
                  >
                    <X className="size-4" />
                  </Button>
                </>
              ) : (
                <>
                  <Button
                    variant="ghost"
                    className="min-w-0 w-full items-start justify-start overflow-hidden text-left font-normal"
                    onClick={(e) => {
                      e.preventDefault();
                      onThreadClick?.(t.thread_id);
                      if (t.thread_id === threadId) return;
                      setThreadId(t.thread_id);
                    }}
                  >
                    <p className="truncate text-ellipsis">{itemText}</p>
                  </Button>
                  <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    className="size-8 shrink-0 text-slate-500 opacity-60 transition-opacity hover:opacity-100"
                    aria-label={`会话操作 ${itemText}`}
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setOpenMenuThreadId((current) =>
                        current === t.thread_id ? null : t.thread_id,
                      );
                    }}
                  >
                    <Ellipsis className="size-4" />
                  </Button>
                  {isMenuOpen && (
                    <div className="absolute top-9 right-0 z-20 w-28 rounded-md border border-slate-200 bg-white py-1 shadow-lg">
                      <Button
                        type="button"
                        variant="ghost"
                        className="h-8 w-full justify-start rounded-none px-3 text-sm"
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          startEditing();
                        }}
                      >
                        <Pencil className="size-4" />
                        重命名
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        className="h-8 w-full justify-start rounded-none px-3 text-sm text-red-600 hover:text-red-700"
                        disabled={isDeleting}
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          void deleteCurrentThread();
                        }}
                      >
                        <Trash2 className="size-4" />
                        删除
                      </Button>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ThreadHistoryLoading() {
  return (
    <div className="flex h-full w-full flex-col items-start justify-start gap-2 overflow-y-scroll [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-gray-300 [&::-webkit-scrollbar-track]:bg-transparent">
      {Array.from({ length: 30 }).map((_, i) => (
        <Skeleton
          key={`skeleton-${i}`}
          className="h-10 w-[280px]"
        />
      ))}
    </div>
  );
}

export default function ThreadHistory() {
  const PAGE_SIZE = 20;
  const isLargeScreen = useMediaQuery("(min-width: 1024px)");
  const [threadId, setThreadId] = useQueryState("threadId");
  const [chatHistoryOpen, setChatHistoryOpen] = useQueryState(
    "chatHistoryOpen",
    parseAsBoolean.withDefault(false),
  );

  const {
    getThreads,
    renameThread,
    deleteThread,
    threadsLoading,
    setThreadsLoading,
  } = useThreads();
  const [page, setPage] = useState(1);
  const [visibleThreads, setVisibleThreads] = useState<Thread[]>([]);
  const [totalThreads, setTotalThreads] = useState(0);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const loadPage = useCallback(
    async (nextPage: number) => {
      if (mountedRef.current) {
        setThreadsLoading(true);
      }
      try {
        const result = await getThreads(nextPage, PAGE_SIZE);
        if (!result || !mountedRef.current) {
          return;
        }
        setVisibleThreads(result.threads);
        setTotalThreads(result.total);
      } finally {
        if (mountedRef.current) {
          setThreadsLoading(false);
        }
      }
    },
    [getThreads, setThreadsLoading],
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    loadPage(page).catch(console.error);
  }, [loadPage, page, threadId]);

  const totalPages = Math.max(1, Math.ceil(totalThreads / PAGE_SIZE));

  const pagination = (
    <div className="mt-auto flex w-full items-center justify-between border-t border-slate-200 px-4 py-3 text-sm text-slate-600">
      <Button
        type="button"
        variant="ghost"
        size="sm"
        disabled={page <= 1 || threadsLoading}
        onClick={() => setPage((current) => Math.max(1, current - 1))}
      >
        <ChevronLeft className="size-4" />
        上一页
      </Button>
      <span>
        第 {page} / {totalPages} 页
      </span>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        aria-label="下一页"
        disabled={page >= totalPages || threadsLoading}
        onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
      >
        下一页
        <ChevronRight className="size-4" />
      </Button>
    </div>
  );

  return (
    <>
      <div className="shadow-inner-right hidden h-screen w-[300px] shrink-0 flex-col items-start justify-start gap-6 border-r-[1px] border-slate-300 lg:flex">
        <div className="flex w-full items-center justify-between px-4 pt-1.5">
          <div className="flex items-center gap-2">
            <Button
              className="hover:bg-gray-100"
              variant="ghost"
              onClick={() => setChatHistoryOpen((p) => !p)}
            >
              {chatHistoryOpen ? (
                <PanelRightOpen className="size-5" />
              ) : (
                <PanelRightClose className="size-5" />
              )}
            </Button>
            <h1 className="text-xl font-semibold tracking-tight whitespace-nowrap">
              历史对话
            </h1>
          </div>
          <Button
            type="button"
            variant="ghost"
            className="gap-2"
            onClick={() => setThreadId(null)}
          >
            <SquarePen className="size-4" />
            新建对话
          </Button>
        </div>
        <div className="flex min-h-0 w-full flex-1 flex-col">
          {threadsLoading ? (
            <ThreadHistoryLoading />
          ) : (
            <ThreadList
              threads={visibleThreads}
              onRenameThread={async (thread, title) => {
                await renameThread(thread, title);
                await loadPage(page);
              }}
              onDeleteThread={async (thread) => {
                await deleteThread(thread);
                const nextPage =
                  page > 1 && visibleThreads.length === 1 ? page - 1 : page;
                if (nextPage !== page) {
                  setPage(nextPage);
                } else {
                  await loadPage(page);
                }
              }}
            />
          )}
          {pagination}
        </div>
      </div>
      <div className="lg:hidden">
        <Sheet
          open={!!chatHistoryOpen && !isLargeScreen}
          onOpenChange={(open) => {
            if (isLargeScreen) return;
            setChatHistoryOpen(open);
          }}
        >
          <SheetContent
            side="left"
            className="flex lg:hidden"
          >
            <SheetHeader>
              <div className="flex items-center justify-between">
                <SheetTitle className="whitespace-nowrap">历史对话</SheetTitle>
                <Button
                  type="button"
                  variant="ghost"
                  className="gap-2"
                  onClick={() => {
                    setThreadId(null);
                    setChatHistoryOpen(false);
                  }}
                >
                  <SquarePen className="size-4" />
                  新建对话
                </Button>
              </div>
            </SheetHeader>
            <div className="flex min-h-0 flex-1 flex-col">
              <ThreadList
                threads={visibleThreads}
                onRenameThread={async (thread, title) => {
                  await renameThread(thread, title);
                  await loadPage(page);
                }}
                onDeleteThread={async (thread) => {
                  await deleteThread(thread);
                  const nextPage =
                    page > 1 && visibleThreads.length === 1 ? page - 1 : page;
                  if (nextPage !== page) {
                    setPage(nextPage);
                  } else {
                    await loadPage(page);
                  }
                }}
                onThreadClick={() => setChatHistoryOpen((o) => !o)}
              />
              {pagination}
            </div>
          </SheetContent>
        </Sheet>
      </div>
    </>
  );
}

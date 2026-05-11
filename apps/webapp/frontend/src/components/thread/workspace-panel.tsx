"use client";

import { useEffect, useRef, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Copy,
  Trash2,
  Download,
  Ellipsis,
  FileIcon,
  Folder,
  FolderOpen,
  LoaderCircle,
  RefreshCw,
  Upload,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  buildWorkspaceAbsolutePath,
  buildWorkspaceDownloadName,
  deleteWorkspacePath,
  downloadWorkspacePath,
  WorkspaceEntry,
} from "@/lib/workspace";
import { useWorkspaceTree } from "@/hooks/use-workspace-tree";

function basename(path: string | null): string {
  if (!path) {
    return "Workspace";
  }
  const segments = path.split("/").filter(Boolean);
  return segments[segments.length - 1] || path;
}

function formatSelectedPath(path: string | null): string {
  if (!path) {
    return "workspace root";
  }
  return path;
}

function WorkspaceActionMenu(props: {
  label: string;
  open: boolean;
  onToggle: () => void;
  onDownload: () => void | Promise<void>;
  onCopyPath: () => void | Promise<void>;
  onDelete?: () => void | Promise<void>;
}) {
  return (
    <div className="relative">
      <Button
        type="button"
        variant="ghost"
        size="sm"
        aria-label={`Workspace actions for ${props.label}`}
        className="size-7 px-0 text-slate-500 hover:text-slate-900"
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          props.onToggle();
        }}
      >
        <Ellipsis className="size-4" />
      </Button>
      {props.open && (
        <div className="absolute top-8 right-0 z-20 w-36 rounded-md border border-slate-200 bg-white py-1 shadow-lg">
          <Button
            type="button"
            variant="ghost"
            className="h-8 w-full justify-start rounded-none px-3 text-sm"
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              void props.onDownload();
            }}
          >
            <Download className="size-4" />
            下载
          </Button>
          <Button
            type="button"
            variant="ghost"
            className="h-8 w-full justify-start rounded-none px-3 text-sm"
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              void props.onCopyPath();
            }}
          >
            <Copy className="size-4" />
            复制路径
          </Button>
          {props.onDelete && (
            <Button
              type="button"
              variant="ghost"
              className="h-8 w-full justify-start rounded-none px-3 text-sm text-rose-600 hover:text-rose-700"
              onClick={(event) => {
                event.preventDefault();
                event.stopPropagation();
                if (props.onDelete) {
                  void props.onDelete();
                }
              }}
            >
              <Trash2 className="size-4" />
              删除
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

function TreeNode(props: {
  entry: WorkspaceEntry;
  depth: number;
  expandedPaths: string[];
  entriesByPath: Record<string, WorkspaceEntry[]>;
  loadingPaths: string[];
  selectedPath: string | null;
  openMenuPath: string | null;
  onSelect: (entry: WorkspaceEntry) => void;
  onToggleDirectory: (entry: WorkspaceEntry) => void | Promise<void>;
  onToggleMenu: (path: string) => void;
  onDownload: (entry: WorkspaceEntry) => void | Promise<void>;
  onCopyPath: (entry: WorkspaceEntry) => void | Promise<void>;
  onDelete: (entry: WorkspaceEntry) => void | Promise<void>;
  onOpenPreview?: (entry: WorkspaceEntry) => void | Promise<void>;
}) {
  const isDirectory = props.entry.type === "directory";
  const isExpanded = props.expandedPaths.includes(props.entry.path);
  const children = props.entriesByPath[props.entry.path] ?? [];
  const isLoading = props.loadingPaths.includes(props.entry.path);
  const selected = props.selectedPath === props.entry.path;
  const isMenuOpen = props.openMenuPath === props.entry.path;

  return (
    <div>
      <div
        className={cn(
          "flex w-full items-center gap-2 rounded-md px-2 py-1 text-sm transition-colors",
          selected ? "bg-slate-200 text-slate-950" : "hover:bg-slate-100",
        )}
        style={{ paddingLeft: `${props.depth * 16 + 8}px` }}
      >
        <button
          type="button"
          className="flex min-w-0 flex-1 items-center gap-2 py-1 text-left"
          onClick={() => {
            props.onSelect(props.entry);
            if (isDirectory) {
              void props.onToggleDirectory(props.entry);
            }
          }}
          onDoubleClick={() => {
            void props.onOpenPreview?.(props.entry);
          }}
        >
          <span className="flex h-4 w-4 items-center justify-center text-slate-500">
            {isDirectory ? (
              isExpanded ? (
                <ChevronDown className="size-4" />
              ) : (
                <ChevronRight className="size-4" />
              )
            ) : (
              <span className="size-4" />
            )}
          </span>
          {isDirectory ? (
            isExpanded ? (
              <FolderOpen className="size-4 text-amber-500" />
            ) : (
              <Folder className="size-4 text-amber-500" />
            )
          ) : (
            <FileIcon className="size-4 text-slate-500" />
          )}
          <span className="min-w-0 flex-1 truncate">{props.entry.name}</span>
          {isLoading && <LoaderCircle className="size-3.5 animate-spin text-slate-400" />}
        </button>
        <WorkspaceActionMenu
          label={props.entry.name}
          open={isMenuOpen}
          onToggle={() => props.onToggleMenu(props.entry.path)}
          onDownload={() => props.onDownload(props.entry)}
          onCopyPath={() => props.onCopyPath(props.entry)}
          onDelete={() => props.onDelete(props.entry)}
        />
      </div>

      {isDirectory && isExpanded && children.length > 0 && (
        <div className="mt-0.5">
          {children.map((child) => (
            <TreeNode
              key={child.path}
              entry={child}
              depth={props.depth + 1}
              expandedPaths={props.expandedPaths}
              entriesByPath={props.entriesByPath}
              loadingPaths={props.loadingPaths}
              selectedPath={props.selectedPath}
              openMenuPath={props.openMenuPath}
              onSelect={props.onSelect}
              onToggleDirectory={props.onToggleDirectory}
              onToggleMenu={props.onToggleMenu}
              onDownload={props.onDownload}
              onCopyPath={props.onCopyPath}
              onDelete={props.onDelete}
              onOpenPreview={props.onOpenPreview}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function WorkspacePanel(props: {
  threadId: string | null;
  className?: string;
  onOpenPreview?: (entry: WorkspaceEntry) => void | Promise<void>;
}) {
  const {
    cwd,
    entriesByPath,
    expandedPaths,
    selectedEntry,
    loadingPaths,
    error,
    uploading,
    refresh,
    toggleDirectory,
    selectEntry,
    uploadFiles,
  } = useWorkspaceTree(props.threadId);
  const [dragOver, setDragOver] = useState(false);
  const [openMenuPath, setOpenMenuPath] = useState<string | null>(null);
  const dragDepth = useRef(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const rootEntry: WorkspaceEntry = {
    name: "workspace",
    path: "",
    type: "directory",
    size: null,
  };

  const rootEntries = entriesByPath[""] ?? [];
  const targetPath =
    selectedEntry?.type === "directory"
      ? selectedEntry.path
      : selectedEntry?.path.includes("/")
        ? selectedEntry.path.slice(0, selectedEntry.path.lastIndexOf("/"))
        : "";

  const handleFiles = async (fileList: FileList | null) => {
    if (!fileList || fileList.length === 0) {
      return;
    }
    const files = Array.from(fileList);
    try {
      const written = await uploadFiles(files);
      toast.success(`Uploaded ${written.length} file(s) to ${formatSelectedPath(targetPath)}.`);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to upload workspace files.",
      );
    }
  };

  const handleCopyPath = async (
    entry: Pick<WorkspaceEntry, "path"> | null,
    label: string,
  ) => {
    const absolutePath = buildWorkspaceAbsolutePath(cwd, entry);
    if (!absolutePath) {
      return;
    }
    try {
      await navigator.clipboard.writeText(absolutePath);
      toast.success(`Copied path for ${label}: ${absolutePath}`);
      setOpenMenuPath(null);
    } catch {
      toast.error("Failed to copy workspace path.");
    }
  };

  const handleDownload = async (
    entry: Pick<WorkspaceEntry, "path">,
    label: string,
  ) => {
    if (!props.threadId) {
      return;
    }
    const target = entry.path;
    try {
      const { blob, filename } = await downloadWorkspacePath(props.threadId, target);
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download =
        filename ?? buildWorkspaceDownloadName(target, props.threadId);
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(objectUrl);
      toast.success(`Downloaded ${label}.`);
      setOpenMenuPath(null);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to download workspace item.",
      );
    }
  };

  const handleDelete = async (
    entry: Pick<WorkspaceEntry, "path" | "type" | "name">,
    label: string,
  ) => {
    if (!props.threadId) {
      return;
    }
    const target = entry.path;
    const parentPath =
      entry.type === "directory"
        ? target.includes("/")
          ? target.slice(0, target.lastIndexOf("/"))
          : ""
        : target.includes("/")
          ? target.slice(0, target.lastIndexOf("/"))
          : "";
    try {
      await deleteWorkspacePath(props.threadId, target);
      await refresh(parentPath);
      toast.success(`Deleted ${label}.`);
      setOpenMenuPath(null);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to delete workspace item.",
      );
    }
  };

  const toggleMenu = (path: string) => {
    setOpenMenuPath((current) => (current === path ? null : path));
  };

  useEffect(() => {
    dragDepth.current = 0;
    setDragOver(false);
    setOpenMenuPath(null);
  }, [props.threadId]);

  useEffect(() => {
    const handleWindowClick = () => setOpenMenuPath(null);
    window.addEventListener("click", handleWindowClick);
    return () => {
      window.removeEventListener("click", handleWindowClick);
    };
  }, []);

  if (!props.threadId) {
    return (
      <div
        className={cn(
          "flex h-full flex-col justify-center bg-slate-50 px-6 text-center",
          props.className,
        )}
      >
        <h2 className="text-base font-semibold text-slate-900">Workspace</h2>
        <p className="mt-2 text-sm text-slate-600">
          先创建或选择一个对话，右侧才会显示该对话的工作目录。
        </p>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex h-full min-w-0 flex-col overflow-hidden bg-slate-50",
        dragOver && "bg-sky-50",
        props.className,
      )}
      onDragEnter={(event) => {
        if (!event.dataTransfer?.types.includes("Files")) {
          return;
        }
        dragDepth.current += 1;
        setDragOver(true);
      }}
      onDragOver={(event) => {
        event.preventDefault();
      }}
      onDragLeave={(event) => {
        if (!event.dataTransfer?.types.includes("Files")) {
          return;
        }
        dragDepth.current -= 1;
        if (dragDepth.current <= 0) {
          dragDepth.current = 0;
          setDragOver(false);
        }
      }}
      onDrop={(event) => {
        event.preventDefault();
        dragDepth.current = 0;
        setDragOver(false);
        void handleFiles(event.dataTransfer.files);
      }}
    >
      <div className="border-b border-slate-200 bg-white px-4 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold text-slate-900">
              {basename(cwd)}
            </h2>
            <p className="mt-1 truncate text-xs text-slate-500">{cwd}</p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              aria-label="Upload files to workspace"
              onClick={() => inputRef.current?.click()}
              disabled={uploading}
            >
              <Upload className="size-4" />
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              aria-label="Refresh workspace tree"
              onClick={() => void refresh()}
              disabled={loadingPaths.includes("") || uploading}
            >
              <RefreshCw
                className={cn(
                  "size-4",
                  loadingPaths.includes("") && "animate-spin",
                )}
              />
            </Button>
          </div>
        </div>
        <p className="mt-3 text-xs text-slate-600">
          Upload target: {formatSelectedPath(targetPath)}
        </p>
        <input
          ref={inputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(event) => {
            void handleFiles(event.target.files);
            event.target.value = "";
          }}
        />
      </div>

      <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-2 py-3">
        <div
          className={cn(
            "mb-2 flex w-full items-center gap-2 rounded-md px-2 py-1 text-sm font-medium transition-colors",
            !selectedEntry ? "bg-slate-200 text-slate-950" : "hover:bg-slate-100",
          )}
        >
          <button
            type="button"
            className="flex min-w-0 flex-1 items-center gap-2 py-1 text-left"
            onClick={() => selectEntry(null)}
          >
            <FolderOpen className="size-4 text-amber-500" />
            <span className="min-w-0 flex-1 truncate">workspace</span>
          </button>
          <WorkspaceActionMenu
            label="workspace"
            open={openMenuPath === ""}
            onToggle={() => toggleMenu("")}
            onDownload={() => handleDownload(rootEntry, "workspace")}
            onCopyPath={() => handleCopyPath(rootEntry, "workspace")}
          />
        </div>

        {dragOver && (
          <div className="mb-3 rounded-lg border border-dashed border-sky-400 bg-sky-100 px-3 py-3 text-sm text-sky-900">
            Drop files here to upload them into {formatSelectedPath(targetPath)}.
          </div>
        )}

        {error && (
          <div className="mb-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
            {error}
          </div>
        )}

        {rootEntries.length === 0 && loadingPaths.includes("") ? (
          <div className="flex items-center gap-2 px-2 py-3 text-sm text-slate-500">
            <LoaderCircle className="size-4 animate-spin" />
            Loading workspace…
          </div>
        ) : rootEntries.length === 0 ? (
          <div className="rounded-lg border border-dashed border-slate-200 bg-white px-3 py-6 text-center text-sm text-slate-500">
            Workspace is empty. Drag files here to upload them.
          </div>
        ) : (
          rootEntries.map((entry) => (
            <TreeNode
              key={entry.path}
              entry={entry}
              depth={0}
              expandedPaths={expandedPaths}
              entriesByPath={entriesByPath}
              loadingPaths={loadingPaths}
              selectedPath={selectedEntry?.path ?? null}
              openMenuPath={openMenuPath}
              onSelect={selectEntry}
              onToggleDirectory={toggleDirectory}
              onToggleMenu={toggleMenu}
              onDownload={(item) => handleDownload(item, item.name)}
              onCopyPath={(item) => handleCopyPath(item, item.name)}
              onDelete={(item) => handleDelete(item, item.name)}
              onOpenPreview={props.onOpenPreview}
            />
          ))
        )}
      </div>
    </div>
  );
}

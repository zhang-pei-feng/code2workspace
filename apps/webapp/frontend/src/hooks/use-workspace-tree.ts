import { useCallback, useEffect, useRef, useState } from "react";

import {
  fetchWorkspaceTree,
  getUploadTargetPath,
  uploadWorkspaceFiles,
  WorkspaceEntry,
} from "@/lib/workspace";

interface SelectedWorkspaceEntry {
  name: string;
  path: string;
  type: "directory" | "file";
}

export function useWorkspaceTree(threadId: string | null) {
  const [cwd, setCwd] = useState<string | null>(null);
  const [entriesByPath, setEntriesByPath] = useState<Record<string, WorkspaceEntry[]>>(
    {},
  );
  const [expandedPaths, setExpandedPaths] = useState<string[]>([]);
  const [selectedEntry, setSelectedEntry] =
    useState<SelectedWorkspaceEntry | null>(null);
  const [loadingPaths, setLoadingPaths] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const entriesByPathRef = useRef<Record<string, WorkspaceEntry[]>>({});

  useEffect(() => {
    entriesByPathRef.current = entriesByPath;
  }, [entriesByPath]);

  const clearState = useCallback(() => {
    setCwd(null);
    setEntriesByPath({});
    entriesByPathRef.current = {};
    setExpandedPaths([]);
    setSelectedEntry(null);
    setLoadingPaths([]);
    setError(null);
    setUploading(false);
  }, []);

  const loadDirectory = useCallback(
    async (path = "", options?: { force?: boolean }): Promise<void> => {
      if (!threadId) {
        return;
      }
      if (!options?.force && entriesByPathRef.current[path]) {
        return;
      }

      setLoadingPaths((current) =>
        current.includes(path) ? current : [...current, path],
      );
      setError(null);
      try {
        const response = await fetchWorkspaceTree(threadId, path);
        setCwd(response.cwd);
        setEntriesByPath((current) => ({
          ...current,
          [response.path]: response.entries,
        }));
      } catch (err) {
        setError(err instanceof Error ? err.message : "workspace_load_failed");
        throw err;
      } finally {
        setLoadingPaths((current) => current.filter((item) => item !== path));
      }
    },
    [threadId],
  );

  const refresh = async (focusPath = ""): Promise<void> => {
    if (!threadId) {
      return;
    }
    const nextExpanded = Array.from(
      new Set(
        expandedPaths.filter(Boolean).concat(focusPath ? [focusPath] : []),
      ),
    ).sort((left, right) => left.split("/").length - right.split("/").length);

    setEntriesByPath({});
    await loadDirectory("", { force: true });
    for (const path of nextExpanded) {
      await loadDirectory(path, { force: true });
    }
  };

  const toggleDirectory = async (entry: WorkspaceEntry): Promise<void> => {
    setSelectedEntry({
      name: entry.name,
      path: entry.path,
      type: entry.type,
    });

    if (entry.type !== "directory") {
      return;
    }
    if (expandedPaths.includes(entry.path)) {
      setExpandedPaths((current) => current.filter((path) => path !== entry.path));
      return;
    }
    setExpandedPaths((current) => [...current, entry.path]);
    await loadDirectory(entry.path);
  };

  const selectEntry = (entry: WorkspaceEntry | null) => {
    if (!entry) {
      setSelectedEntry(null);
      return;
    }
    setSelectedEntry({
      name: entry.name,
      path: entry.path,
      type: entry.type,
    });
  };

  const uploadFiles = async (files: File[]): Promise<WorkspaceEntry[]> => {
    if (!threadId) {
      throw new Error("thread_required");
    }
    const targetPath = getUploadTargetPath(selectedEntry);
    setUploading(true);
    setError(null);
    try {
      const response = await uploadWorkspaceFiles(threadId, targetPath, files);
      await refresh(targetPath);
      return response.files.map((file) => ({
        name: file.name,
        path: file.path,
        size: file.size,
        type: "file" as const,
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "workspace_upload_failed");
      throw err;
    } finally {
      setUploading(false);
    }
  };

  useEffect(() => {
    clearState();
    if (!threadId) {
      return;
    }
    void loadDirectory("", { force: true });
  }, [threadId, clearState, loadDirectory]);

  return {
    cwd,
    entriesByPath,
    expandedPaths,
    selectedEntry,
    loadingPaths,
    error,
    uploading,
    loadDirectory,
    refresh,
    toggleDirectory,
    selectEntry,
    uploadFiles,
  };
}

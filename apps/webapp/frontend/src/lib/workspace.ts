export interface WorkspaceEntry {
  name: string;
  path: string;
  type: "directory" | "file";
  size: number | null;
}

export interface WorkspaceTreeResponse {
  cwd: string;
  path: string;
  entries: WorkspaceEntry[];
}

export interface WorkspaceUploadResponse {
  cwd: string;
  path: string;
  files: Array<{
    name: string;
    path: string;
    size: number;
  }>;
}

export interface WorkspaceFileResponse {
  cwd: string;
  path: string;
  content: string;
  truncated: boolean;
}

export type WorkspacePreviewKind =
  | "text"
  | "image"
  | "pdf"
  | "docx"
  | "unsupported";

const PREVIEWABLE_TEXT_EXTENSIONS = new Set([
  ".txt",
  ".md",
  ".json",
  ".yaml",
  ".yml",
  ".toml",
  ".ini",
  ".cfg",
  ".conf",
  ".log",
  ".csv",
  ".tsv",
  ".py",
  ".sh",
  ".bash",
  ".zsh",
  ".js",
  ".jsx",
  ".ts",
  ".tsx",
  ".css",
  ".scss",
  ".html",
  ".xml",
  ".sql",
  ".r",
  ".c",
  ".cc",
  ".cpp",
  ".h",
  ".hpp",
  ".java",
  ".go",
  ".rs",
]);

const PREVIEWABLE_IMAGE_EXTENSIONS = new Set([
  ".png",
  ".jpg",
  ".jpeg",
  ".gif",
  ".webp",
  ".bmp",
  ".svg",
]);

const PREVIEWABLE_FILENAMES = new Set([
  "dockerfile",
  "makefile",
  "readme",
  "readme.md",
  "license",
  ".gitignore",
  ".env",
  "agents.md",
]);

function buildWorkspaceQuery(path = ""): string {
  const query = new URLSearchParams();
  if (path) {
    query.set("path", path);
  }
  return query.toString();
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.error ?? detail;
    } catch {
      // ignore malformed error bodies
    }
    throw new Error(detail || "request_failed");
  }
  return (await response.json()) as T;
}

export async function fetchWorkspaceTree(
  threadId: string,
  path = "",
): Promise<WorkspaceTreeResponse> {
  const response = await fetch(
    `/api/threads/${threadId}/workspace/tree?${buildWorkspaceQuery(path)}`,
  );
  return parseResponse<WorkspaceTreeResponse>(response);
}

export async function uploadWorkspaceFiles(
  threadId: string,
  path: string,
  files: File[],
): Promise<WorkspaceUploadResponse> {
  const formData = new FormData();
  formData.set("path", path);
  for (const file of files) {
    formData.append("files", file);
  }

  const response = await fetch(`/api/threads/${threadId}/workspace/upload`, {
    method: "POST",
    body: formData,
  });
  return parseResponse<WorkspaceUploadResponse>(response);
}

export async function fetchWorkspaceFile(
  threadId: string,
  path: string,
): Promise<WorkspaceFileResponse> {
  const response = await fetch(
    `/api/threads/${threadId}/workspace/file?${buildWorkspaceQuery(path)}`,
  );
  return parseResponse<WorkspaceFileResponse>(response);
}

export function getUploadTargetPath(
  selectedEntry: Pick<WorkspaceEntry, "path" | "type"> | null,
): string {
  if (!selectedEntry) {
    return "";
  }
  if (selectedEntry.type === "directory") {
    return selectedEntry.path;
  }
  const lastSlashIndex = selectedEntry.path.lastIndexOf("/");
  return lastSlashIndex === -1
    ? ""
    : selectedEntry.path.slice(0, lastSlashIndex);
}

export function isPreviewableWorkspaceEntry(
  entry: Pick<WorkspaceEntry, "name" | "type" | "size">,
): boolean {
  return getWorkspacePreviewKind(entry) !== "unsupported";
}

export function getWorkspacePreviewKind(
  entry: Pick<WorkspaceEntry, "name" | "type" | "size">,
): WorkspacePreviewKind {
  if (entry.type !== "file") {
    return "unsupported";
  }
  const normalizedName = entry.name.toLowerCase();
  const dotIndex = normalizedName.lastIndexOf(".");
  const extension = dotIndex === -1 ? "" : normalizedName.slice(dotIndex);

  if (
    PREVIEWABLE_IMAGE_EXTENSIONS.has(extension) &&
    (entry.size === null || entry.size <= 10_000_000)
  ) {
    return "image";
  }
  if (extension === ".pdf" && (entry.size === null || entry.size <= 20_000_000)) {
    return "pdf";
  }
  if (extension === ".docx" && (entry.size === null || entry.size <= 10_000_000)) {
    return "docx";
  }
  if (entry.size !== null && entry.size > 100_000) {
    return "unsupported";
  }
  if (PREVIEWABLE_FILENAMES.has(normalizedName)) {
    return "text";
  }
  if (dotIndex === -1) {
    return "unsupported";
  }
  return PREVIEWABLE_TEXT_EXTENSIONS.has(extension) ? "text" : "unsupported";
}

export function buildWorkspaceAbsolutePath(
  cwd: string | null,
  selectedEntry: Pick<WorkspaceEntry, "path"> | null,
): string {
  if (!cwd) {
    return "";
  }
  if (!selectedEntry?.path) {
    return cwd;
  }
  return `${cwd}/${selectedEntry.path}`;
}

export function parseDownloadFilename(
  contentDisposition: string | null,
): string | null {
  if (!contentDisposition) {
    return null;
  }
  const match = contentDisposition.match(/filename="?([^"]+)"?/i);
  return match?.[1] ?? null;
}

export function buildWorkspaceDownloadName(
  path: string,
  threadId: string,
): string {
  if (!path) {
    return `${threadId}-workspace.zip`;
  }
  const name = path.split("/").filter(Boolean).pop() ?? threadId;
  return name.includes(".") ? name : `${name}.zip`;
}

export async function downloadWorkspacePath(
  threadId: string,
  path: string,
): Promise<{ blob: Blob; filename: string | null }> {
  const response = await fetch(
    `/api/threads/${threadId}/workspace/download?${buildWorkspaceQuery(path)}`,
  );
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.error ?? detail;
    } catch {
      // ignore malformed error bodies
    }
    throw new Error(detail || "request_failed");
  }
  return {
    blob: await response.blob(),
    filename: parseDownloadFilename(response.headers.get("content-disposition")),
  };
}

export async function deleteWorkspacePath(
  threadId: string,
  path: string,
): Promise<void> {
  const response = await fetch(
    `/api/threads/${threadId}/workspace/item?${buildWorkspaceQuery(path)}`,
    { method: "DELETE" },
  );
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.error ?? detail;
    } catch {
      // ignore malformed error bodies
    }
    throw new Error(detail || "request_failed");
  }
}

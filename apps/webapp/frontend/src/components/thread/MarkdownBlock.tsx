import "@assistant-ui/react-markdown/styles/dot.css";

import { MarkdownTextPrimitive } from "@assistant-ui/react-markdown";
import remarkGfm from "remark-gfm";

export function MarkdownBlock() {
  return (
    <MarkdownTextPrimitive
      className="aui-md prose prose-neutral max-w-none text-sm leading-7 prose-headings:mb-2 prose-headings:mt-4 prose-p:my-2 prose-pre:rounded-2xl prose-pre:border prose-pre:border-[var(--line)] prose-pre:bg-[var(--panel-strong)] prose-pre:px-4 prose-pre:py-3 prose-code:rounded prose-code:bg-[var(--panel-strong)] prose-code:px-1 prose-code:py-0.5 prose-code:text-[var(--ink)] prose-a:text-[var(--accent-strong)] prose-blockquote:border-l-[var(--accent-strong)] prose-blockquote:text-[var(--muted-ink)]"
      remarkPlugins={[remarkGfm]}
    />
  );
}

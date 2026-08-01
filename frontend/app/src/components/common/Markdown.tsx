import { memo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import s from "./markdown.module.css";

// Hoisted: rebuilding this object per render hands react-markdown a new prop
// every time, for no gain.
const COMPONENTS: Components = {
  a: ({ node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
};

const PLUGINS = [remarkGfm];

/**
 * Renders assistant/message text as Markdown on the parchment surface.
 *
 * The model is prompted to reply conversationally with *light* Markdown (a bold
 * lead-in, the occasional list or code block), so streamed replies read like
 * someone talking back instead of a wall of literal `**` and `-` characters.
 * GFM is enabled for tables/strikethrough; links open safely in a new tab.
 *
 * Memoised on the body string — load-bearing, not tidiness. A streaming turn
 * re-renders the whole thread on every token, so without this each message in a
 * 60-turn thread is re-parsed into an AST once per token of the reply.
 * `children` is a primitive, so the comparison holds even though the message
 * objects upstream are mutated in place rather than replaced.
 */
export const Markdown = memo(function Markdown({ children }: { children: string }) {
  return (
    <div className={s.md}>
      <ReactMarkdown remarkPlugins={PLUGINS} components={COMPONENTS}>
        {children}
      </ReactMarkdown>
    </div>
  );
});

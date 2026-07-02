import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import s from "./markdown.module.css";

/**
 * Renders assistant/message text as Markdown on the parchment surface.
 *
 * The model is prompted to reply conversationally with *light* Markdown (a bold
 * lead-in, the occasional list or code block), so streamed replies read like
 * someone talking back instead of a wall of literal `**` and `-` characters.
 * GFM is enabled for tables/strikethrough; links open safely in a new tab.
 */
export function Markdown({ children }: { children: string }) {
  return (
    <div className={s.md}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ node, ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer" />
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";


type MarkdownContentProps = {
  content: string;
  className?: string;
};


export default function MarkdownContent({
  content,
  className = "",
}: MarkdownContentProps) {
  return (
    <div className={`markdown-body ${className}`.trim()}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>
        {content}
      </ReactMarkdown>
    </div>
  );
}

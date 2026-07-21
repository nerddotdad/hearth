import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

type Props = {
  content: string
}

/** Render assistant replies as GitHub-flavored markdown (safe defaults). */
export function AgentMarkdown({ content }: Props) {
  const text = content || ''
  if (!text.trim()) {
    return <span className="muted">(empty)</span>
  }
  return (
    <div className="agent-md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  )
}

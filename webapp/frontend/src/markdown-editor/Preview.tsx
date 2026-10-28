import { marked } from 'marked'
import { useMemo } from 'react'

// Loaded on first use, so marked stays out of the main bundle.
// Raw HTML in the text is rendered as-is: the app is local and single-user (#34).
export default function Preview({ markdown }: { markdown: string }) {
  const html = useMemo(() => marked.parse(markdown, { async: false, gfm: true }), [markdown])
  return <div className="markdown-prose" dangerouslySetInnerHTML={{ __html: html }} />
}

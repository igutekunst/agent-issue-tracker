// Shared markdown renderer used by issue descriptions and knowledge values.
import { marked } from 'marked'
import DOMPurify from 'dompurify'

marked.setOptions({ gfm: true, breaks: true })

export function renderMarkdown(src) {
  if (!src || !String(src).trim()) return ''
  return DOMPurify.sanitize(marked.parse(String(src)))
}

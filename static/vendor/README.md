Vendored for offline assistant-message Markdown rendering:

- Marked 17.0.1: https://marked.js.org/ (MIT; marked-LICENSE.md)
  Source: https://cdn.jsdelivr.net/npm/marked@17.0.1/lib/marked.umd.js
- DOMPurify 3.3.3: https://github.com/cure53/DOMPurify (Apache-2.0 OR MPL-2.0; DOMPurify-LICENSE)
  Source: https://cdn.jsdelivr.net/npm/dompurify@3.3.3/dist/purify.min.js

Parsed Markdown is sanitized with a formatting-only allowlist before insertion.
Images and interactive HTML are excluded; image cards use the existing renderers.
User messages and raw tool logs remain plain text.

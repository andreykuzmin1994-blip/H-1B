'use client';

import { useState } from 'react';

export function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition ${
        copied
          ? 'bg-lime-600 text-white'
          : 'bg-ink-900 text-white hover:bg-ink-800'
      }`}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        } catch {
          /* clipboard unavailable */
        }
      }}
    >
      {copied ? (
        <>
          <svg width="12" height="12" viewBox="0 0 20 20" fill="currentColor">
            <path d="M16.7 5.3a1 1 0 010 1.4l-8 8a1 1 0 01-1.4 0l-4-4a1 1 0 011.4-1.4L8 12.6l7.3-7.3a1 1 0 011.4 0z" />
          </svg>
          Copied
        </>
      ) : (
        <>
          <svg width="12" height="12" viewBox="0 0 20 20" fill="currentColor">
            <path d="M7 2a2 2 0 00-2 2v10a2 2 0 002 2h6a2 2 0 002-2V4a2 2 0 00-2-2H7zm0 1h6a1 1 0 011 1v10a1 1 0 01-1 1H7a1 1 0 01-1-1V4a1 1 0 011-1zm-3 3a2 2 0 012-2v1a1 1 0 00-1 1v10a1 1 0 001 1h6a1 1 0 001-1v0a2 2 0 01-2 2H6a2 2 0 01-2-2V6z" />
          </svg>
          Copy
        </>
      )}
    </button>
  );
}

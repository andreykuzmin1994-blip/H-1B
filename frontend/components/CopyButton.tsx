'use client';

import { useState } from 'react';

export function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      className="rounded bg-gray-900 px-3 py-1 text-xs text-white"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        } catch (e) {
          // clipboard unavailable – no-op
        }
      }}
    >
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
}

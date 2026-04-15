'use client';

import { useState } from 'react';

/**
 * Copies either the page's full URL (default) or an explicit path to the
 * clipboard. Falls back gracefully when `navigator.clipboard` is unavailable.
 */
export function ShareButton({
  path,
  label = 'Share link',
  variant = 'outline',
}: {
  path?: string;
  label?: string;
  variant?: 'outline' | 'ghost' | 'primary';
}) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    const target =
      path ??
      (typeof window !== 'undefined' ? window.location.href : '');
    try {
      const href =
        typeof window !== 'undefined' && path && path.startsWith('/')
          ? `${window.location.origin}${path}`
          : target;
      await navigator.clipboard.writeText(href);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable */
    }
  };

  const base =
    variant === 'primary'
      ? 'bg-ink-900 text-white hover:bg-ink-800'
      : variant === 'ghost'
      ? 'text-ink-700 hover:bg-ink-100'
      : 'border border-white/20 bg-white/5 text-white hover:bg-white/10';

  return (
    <button
      type="button"
      onClick={copy}
      className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition ${base}`}
    >
      {copied ? (
        <>
          <svg width="12" height="12" viewBox="0 0 20 20" fill="currentColor">
            <path d="M16.7 5.3a1 1 0 010 1.4l-8 8a1 1 0 01-1.4 0l-4-4a1 1 0 011.4-1.4L8 12.6l7.3-7.3a1 1 0 011.4 0z" />
          </svg>
          Link copied
        </>
      ) : (
        <>
          <svg width="12" height="12" viewBox="0 0 20 20" fill="currentColor">
            <path d="M11 3a1 1 0 100 2h2.586l-5.293 5.293a1 1 0 001.414 1.414L15 6.414V9a1 1 0 102 0V4a1 1 0 00-1-1h-5zM5 5a2 2 0 00-2 2v8a2 2 0 002 2h8a2 2 0 002-2v-3a1 1 0 10-2 0v3H5V7h3a1 1 0 000-2H5z" />
          </svg>
          {label}
        </>
      )}
    </button>
  );
}

'use client';

import { useState } from 'react';

/**
 * Copies either the page's full URL (default) or an explicit path to the
 * clipboard. Styled as a plain text button, not a chip.
 */
export function ShareButton({
  path,
  label = 'Copy link',
}: {
  path?: string;
  label?: string;
}) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      const href =
        typeof window !== 'undefined' && path && path.startsWith('/')
          ? `${window.location.origin}${path}`
          : typeof window !== 'undefined'
          ? window.location.href
          : '';
      await navigator.clipboard.writeText(href);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable */
    }
  };

  return (
    <button type="button" onClick={copy} className="btn-text text-sm">
      {copied ? 'Link copied' : label}
    </button>
  );
}

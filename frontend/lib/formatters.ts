export function formatCurrency(value: number | null | undefined): string {
  if (value == null) return '-';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(Number(value));
}

export function severityClass(score: number): string {
  if (score >= 75) return 'bg-critical';
  if (score >= 50) return 'bg-high';
  if (score >= 25) return 'bg-medium';
  return 'bg-low';
}

export function severityLabel(score: number): string {
  if (score >= 75) return 'CRITICAL';
  if (score >= 50) return 'HIGH';
  if (score >= 25) return 'MEDIUM';
  return 'LOW';
}

export function addressHash(parts: { address_line1?: string | null; city?: string | null; state?: string | null; zip?: string | null }): string {
  const s = [parts.address_line1, parts.city, parts.state, parts.zip]
    .filter(Boolean)
    .map((s) => (s ?? '').toUpperCase().trim())
    .join('|');
  // Simple DJB2 hash for URL-safe identifier
  let hash = 5381;
  for (let i = 0; i < s.length; i++) {
    hash = ((hash << 5) + hash) ^ s.charCodeAt(i);
  }
  return (hash >>> 0).toString(16);
}

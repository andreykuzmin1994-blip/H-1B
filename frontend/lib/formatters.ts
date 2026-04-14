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


export function formatCurrency(value: number | null | undefined): string {
  if (value == null) return '-';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(Number(value));
}

/**
 * Legacy class kept for components that still expect a single colored-background
 * chip (old design). The severity-badge CSS falls back gracefully.
 */
export function severityClass(score: number): string {
  if (score >= 75) return 'sev-critical';
  if (score >= 50) return 'sev-high';
  if (score >= 25) return 'sev-medium';
  return 'sev-low';
}

/** Dot color used inside the new pill design. */
export function severityDotClass(score: number): string {
  if (score >= 75) return 'bg-red-600';
  if (score >= 50) return 'bg-orange-500';
  if (score >= 25) return 'bg-amber-500';
  return 'bg-lime-500';
}

export function severityLabel(score: number): string {
  if (score >= 75) return 'Critical';
  if (score >= 50) return 'High';
  if (score >= 25) return 'Medium';
  return 'Low';
}

export function severityTagline(score: number): string {
  if (score >= 75) return 'Multiple strong indicators of abuse';
  if (score >= 50) return 'Several concerning patterns detected';
  if (score >= 25) return 'Mild anomalies worth a second look';
  return 'Within expected patterns';
}

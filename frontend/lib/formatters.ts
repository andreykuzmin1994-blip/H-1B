export function formatCurrency(value: number | null | undefined): string {
  if (value == null) return '—';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(Number(value));
}

export function severityClass(score: number): string {
  if (score >= 75) return 'sev-critical';
  if (score >= 50) return 'sev-high';
  if (score >= 25) return 'sev-medium';
  return 'sev-low';
}

export function severityMarkClass(score: number): string {
  if (score >= 75) return 'mark-critical';
  if (score >= 50) return 'mark-high';
  if (score >= 25) return 'mark-medium';
  return 'mark-low';
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

/** Tokenised severity for components that still need a dot color by name. */
export function severityToken(
  sev: string | null | undefined,
): 'critical' | 'high' | 'medium' | 'low' {
  switch ((sev ?? '').toUpperCase()) {
    case 'CRITICAL':
      return 'critical';
    case 'HIGH':
      return 'high';
    case 'MEDIUM':
      return 'medium';
    default:
      return 'low';
  }
}

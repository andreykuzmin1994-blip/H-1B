import { prisma } from '@/lib/db';
import { formatCurrency } from '@/lib/formatters';

const FLAG_TO_VIOLATION: Record<string, string> = {
  NAICS_SOC_MISMATCH: 'Misrepresentation of job duties (NAICS-SOC mismatch)',
  NON_SPECIALTY_SOC:
    'Filing for occupation that does not qualify as a specialty occupation under INA 214(i)',
  WAGE_FAR_BELOW_SOC_MEDIAN:
    'Offered wage far below SOC national median (20 CFR 655.731)',
  WAGE_BELOW_PREVAILING: 'Offered wage below DOL prevailing wage (20 CFR 655.731)',
  RESIDENTIAL_ADDRESS: 'Questionable business presence at stated address',
  SHARED_ADDRESS_CLUSTER: 'Multiple entities filing from same address (possible shell company cluster)',
  VIRTUAL_OFFICE: 'Employer address is a virtual office / mail forwarding provider',
  NEW_ENTITY_IMMEDIATE_FILING:
    'Entity formed within 90 days of first LCA filing (possible shell entity)',
  STAFFING_NO_CLIENT: 'Staffing / consulting filer with no secondary entity listed',
  HIGH_DENIAL_RATE: 'USCIS denial rate >2x SOC peer average',
  VOLUME_SPIKE: 'Filing volume increased >300% year-over-year',
  POST_SANCTION_FILING: 'Continued H-1B activity after enforcement sanction',
  CONNECTED_TO_VIOLATOR: 'Entity linked to known H-1B violator through shared agent/address/officer',
};

export async function buildTipPackage(employerId: number) {
  const employer = await prisma.employer.findUniqueOrThrow({
    where: { id: employerId },
    include: {
      flags: { orderBy: { flag_score: 'desc' } },
      violations: true,
      filings: { take: 5, orderBy: { received_date: 'desc' } },
    },
  });

  const address = [employer.address_line1, employer.city, employer.state, employer.zip]
    .filter(Boolean)
    .join(', ');

  const flags = employer.flags;
  const alleged = Array.from(
    new Set(flags.map((f) => FLAG_TO_VIOLATION[f.flag_type] ?? f.flag_type)),
  );

  const dolLines: string[] = [];
  dolLines.push(`Employer: ${employer.name}`);
  if (employer.ein) dolLines.push(`EIN (last 4): ${employer.ein.slice(-4)}`);
  dolLines.push(`Address: ${address}`);
  dolLines.push('');
  dolLines.push('Alleged violations under 20 CFR § 655:');
  for (const a of alleged) dolLines.push(`  - ${a}`);
  dolLines.push('');
  dolLines.push('Supporting public-data evidence:');
  for (const f of flags) {
    dolLines.push(
      `  - [${f.flag_severity}] ${f.flag_type}: ${f.description ?? ''}`.trim(),
    );
  }
  if (employer.filings.length > 0) {
    dolLines.push('');
    dolLines.push('Recent LCAs referenced:');
    for (const f of employer.filings) {
      dolLines.push(
        `  - Case ${f.case_number}: ${f.soc_code} ${f.job_title ?? ''} · ${formatCurrency(
          f.wage_annualized ? Number(f.wage_annualized) : null,
        )} (annualized)`,
      );
    }
  }

  const uscisLines: string[] = [];
  uscisLines.push(
    `I am submitting this tip based on publicly available DOL OFLC, USCIS, DOL WHD, and BLS OEWS data indicating the following anomalies for the employer identified above:`,
  );
  uscisLines.push('');
  for (const f of flags) {
    uscisLines.push(`- [${f.flag_severity}] ${f.description ?? f.flag_type}`);
  }
  if (employer.violations.length > 0) {
    uscisLines.push('');
    uscisLines.push('Prior DOL/USCIS enforcement records:');
    for (const v of employer.violations) {
      uscisLines.push(
        `- ${v.source} (${v.violation_date?.toISOString().slice(0, 10) ?? 'date unknown'}): ${v.violation_type ?? ''}`.trim(),
      );
    }
  }

  const evidenceLines: string[] = [];
  evidenceLines.push(`Employer: ${employer.name}`);
  evidenceLines.push(`Anomaly score: ${Number(employer.anomaly_score).toFixed(0)} / 100`);
  evidenceLines.push(`Flags: ${flags.length}`);
  evidenceLines.push(`LCA filings on file: ${employer.total_lca_count}`);
  evidenceLines.push(`Prior enforcement records: ${employer.violations.length}`);
  evidenceLines.push('');
  evidenceLines.push('Data sources:');
  evidenceLines.push('  - DOL OFLC LCA Disclosure Data (dol.gov/agencies/eta/foreign-labor/performance)');
  evidenceLines.push('  - USCIS H-1B Employer Data Hub (uscis.gov/tools/reports-and-studies)');
  evidenceLines.push('  - DOL WHD Enforcement Database (enforcedata.dol.gov)');
  evidenceLines.push('  - BLS OEWS Wage Estimates (bls.gov/oes)');

  return {
    dolText: dolLines.join('\n'),
    uscisText: uscisLines.join('\n'),
    evidence: evidenceLines.join('\n'),
  };
}

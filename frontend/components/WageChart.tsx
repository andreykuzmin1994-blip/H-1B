'use client';

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

interface WageRow {
  soc: string;
  employer: number;
  median: number | null;
}

export function WageChart({ data }: { data: WageRow[] }) {
  const prepared = data.map((d) => ({
    soc: d.soc,
    Employer: d.employer,
    'National Median': d.median ?? 0,
  }));
  return (
    <div style={{ width: '100%', height: 260 }}>
      <ResponsiveContainer>
        <BarChart data={prepared}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="soc" />
          <YAxis tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
          <Tooltip
            formatter={(value: number) => `$${Number(value).toLocaleString()}`}
          />
          <Legend />
          <Bar dataKey="Employer" fill="#dc2626" />
          <Bar dataKey="National Median" fill="#0ea5e9" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

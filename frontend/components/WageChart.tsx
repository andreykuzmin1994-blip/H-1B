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

const TICK = { fill: '#536079', fontSize: 11 };

export function WageChart({ data }: { data: WageRow[] }) {
  const prepared = data.map((d) => ({
    soc: d.soc,
    Employer: d.employer,
    'National Median': d.median ?? 0,
  }));
  return (
    <div style={{ width: '100%', height: 260 }}>
      <ResponsiveContainer>
        <BarChart data={prepared} margin={{ top: 4, right: 8, bottom: 0, left: -4 }}>
          <CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" />
          <XAxis dataKey="soc" tick={TICK} stroke="#d6dae3" />
          <YAxis
            tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
            tick={TICK}
            stroke="#d6dae3"
          />
          <Tooltip
            contentStyle={{ borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 12 }}
            formatter={(value: number) => `$${Number(value).toLocaleString()}`}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Bar dataKey="Employer" fill="#b91c1c" radius={[4, 4, 0, 0]} />
          <Bar dataKey="National Median" fill="#28334a" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

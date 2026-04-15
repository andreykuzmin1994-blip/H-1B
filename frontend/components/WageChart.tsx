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

const TICK = { fill: '#5e5b52', fontSize: 11, fontFamily: 'IBM Plex Mono, monospace' };
const TOOLTIP_STYLE = {
  background: '#f4f1ea',
  border: '1px solid #111111',
  borderRadius: 0,
  fontSize: 12,
  color: '#111111',
};

export function WageChart({ data }: { data: WageRow[] }) {
  const prepared = data.map((d) => ({
    soc: d.soc,
    Employer: d.employer,
    'National median': d.median ?? 0,
  }));
  return (
    <div style={{ width: '100%', height: 260 }}>
      <ResponsiveContainer>
        <BarChart data={prepared} margin={{ top: 4, right: 8, bottom: 0, left: -4 }}>
          <CartesianGrid stroke="#d8d5cc" strokeDasharray="2 3" />
          <XAxis dataKey="soc" tick={TICK} stroke="#bab6ac" />
          <YAxis
            tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
            tick={TICK}
            stroke="#bab6ac"
          />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            formatter={(value: number) => `$${Number(value).toLocaleString()}`}
          />
          <Legend wrapperStyle={{ fontSize: 11, color: '#5e5b52' }} />
          <Bar dataKey="Employer" fill="#9a1f1f" />
          <Bar dataKey="National median" fill="#252421" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

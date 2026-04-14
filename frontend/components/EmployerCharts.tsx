'use client';

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

export interface EmployerChartData {
  byYear: { year: number; count: number }[];
  bySoc: { soc: string; count: number }[];
  uscisByYear: { year: number; approvals: number; denials: number }[];
}

const TICK = { fill: '#536079', fontSize: 11 };
const GRID = { stroke: '#e5e7eb' };

export function EmployerCharts({ byYear, bySoc, uscisByYear }: EmployerChartData) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
      <div className="card">
        <h3 className="text-sm font-semibold text-ink-900">Filings per fiscal year</h3>
        <p className="mb-3 text-xs text-ink-500">LCA volume trend</p>
        {byYear.length === 0 ? (
          <p className="text-xs text-ink-500">No filings with a fiscal year yet.</p>
        ) : (
          <div style={{ width: '100%', height: 200 }}>
            <ResponsiveContainer>
              <LineChart data={byYear} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
                <CartesianGrid {...GRID} strokeDasharray="3 3" />
                <XAxis dataKey="year" tick={TICK} stroke="#d6dae3" />
                <YAxis allowDecimals={false} tick={TICK} stroke="#d6dae3" />
                <Tooltip
                  contentStyle={{ borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 12 }}
                />
                <Line
                  type="monotone"
                  dataKey="count"
                  stroke="#f97316"
                  strokeWidth={2}
                  dot={{ r: 3, fill: '#f97316' }}
                  activeDot={{ r: 5 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      <div className="card">
        <h3 className="text-sm font-semibold text-ink-900">Top SOC codes</h3>
        <p className="mb-3 text-xs text-ink-500">By filing volume</p>
        {bySoc.length === 0 ? (
          <p className="text-xs text-ink-500">No SOC data.</p>
        ) : (
          <div style={{ width: '100%', height: 200 }}>
            <ResponsiveContainer>
              <BarChart data={bySoc} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
                <CartesianGrid {...GRID} strokeDasharray="3 3" />
                <XAxis dataKey="soc" tick={TICK} stroke="#d6dae3" />
                <YAxis allowDecimals={false} tick={TICK} stroke="#d6dae3" />
                <Tooltip
                  contentStyle={{ borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 12 }}
                />
                <Bar dataKey="count" fill="#28334a" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      <div className="card">
        <h3 className="text-sm font-semibold text-ink-900">USCIS approvals vs denials</h3>
        <p className="mb-3 text-xs text-ink-500">Initial decisions, by year</p>
        {uscisByYear.length === 0 ? (
          <p className="text-xs text-ink-500">No USCIS data for this employer.</p>
        ) : (
          <div style={{ width: '100%', height: 200 }}>
            <ResponsiveContainer>
              <BarChart data={uscisByYear} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
                <CartesianGrid {...GRID} strokeDasharray="3 3" />
                <XAxis dataKey="year" tick={TICK} stroke="#d6dae3" />
                <YAxis allowDecimals={false} tick={TICK} stroke="#d6dae3" />
                <Tooltip
                  contentStyle={{ borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 12 }}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="approvals" stackId="a" fill="#65a30d" radius={[0, 0, 0, 0]} />
                <Bar dataKey="denials" stackId="a" fill="#b91c1c" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}

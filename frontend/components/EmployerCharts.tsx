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

export function EmployerCharts({ byYear, bySoc, uscisByYear }: EmployerChartData) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
      <div className="card">
        <h3 className="mb-2 text-sm font-semibold">Filings per fiscal year</h3>
        {byYear.length === 0 ? (
          <p className="text-xs text-gray-500">No filings with a fiscal year yet.</p>
        ) : (
          <div style={{ width: '100%', height: 200 }}>
            <ResponsiveContainer>
              <LineChart data={byYear}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="year" />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Line type="monotone" dataKey="count" stroke="#0ea5e9" dot />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      <div className="card">
        <h3 className="mb-2 text-sm font-semibold">Top SOC codes (by volume)</h3>
        {bySoc.length === 0 ? (
          <p className="text-xs text-gray-500">No SOC data.</p>
        ) : (
          <div style={{ width: '100%', height: 200 }}>
            <ResponsiveContainer>
              <BarChart data={bySoc}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="soc" />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="count" fill="#6366f1" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      <div className="card">
        <h3 className="mb-2 text-sm font-semibold">USCIS initial approvals vs denials</h3>
        {uscisByYear.length === 0 ? (
          <p className="text-xs text-gray-500">No USCIS data for this employer.</p>
        ) : (
          <div style={{ width: '100%', height: 200 }}>
            <ResponsiveContainer>
              <BarChart data={uscisByYear}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="year" />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Legend />
                <Bar dataKey="approvals" stackId="a" fill="#10b981" />
                <Bar dataKey="denials" stackId="a" fill="#dc2626" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}

'use client';

import { useEffect, useMemo, useRef } from 'react';
import * as d3 from 'd3';

interface Node {
  id: number;
  name: string;
  state: string | null;
  anomaly_score: number;
  is_violator: boolean;
  depth: number;
}

interface Edge {
  source: number;
  target: number;
  type: string;
  confidence: number;
}

export function EntityGraph({
  graph,
  centerId,
}: {
  graph: { nodes: Node[]; edges: Edge[] };
  centerId: number;
}) {
  const svgRef = useRef<SVGSVGElement>(null);

  // Force simulation requires separate node/edge objects d3 can mutate.
  const data = useMemo(
    () => ({
      nodes: graph.nodes.map((n) => ({ ...n })),
      links: graph.edges.map((e) => ({ ...e })),
    }),
    [graph],
  );

  useEffect(() => {
    if (!svgRef.current || data.nodes.length === 0) return;

    const width = 680;
    const height = 360;

    const svg = d3.select(svgRef.current).attr('viewBox', `0 0 ${width} ${height}`);
    svg.selectAll('*').remove();

    const simulation = d3
      .forceSimulation(data.nodes as any)
      .force(
        'link',
        d3
          .forceLink(data.links as any)
          .id((d: any) => d.id)
          .distance(80),
      )
      .force('charge', d3.forceManyBody().strength(-260))
      .force('center', d3.forceCenter(width / 2, height / 2));

    const link = svg
      .append('g')
      .attr('stroke', '#94a3b8')
      .attr('stroke-opacity', 0.6)
      .selectAll('line')
      .data(data.links)
      .enter()
      .append('line')
      .attr('stroke-width', (d) => 1 + d.confidence * 2);

    const node = svg
      .append('g')
      .selectAll('circle')
      .data(data.nodes)
      .enter()
      .append('circle')
      .attr('r', (d) => (d.id === centerId ? 14 : 8))
      .attr('fill', (d) => {
        if (d.is_violator) return '#dc2626';
        if (d.id === centerId) return '#0ea5e9';
        if (d.anomaly_score >= 50) return '#f97316';
        if (d.anomaly_score >= 25) return '#eab308';
        return '#a3e635';
      })
      .attr('stroke', '#111827')
      .attr('stroke-width', 1);

    node.append('title').text((d) => `${d.name} (${d.state}) · score ${d.anomaly_score.toFixed(0)}`);

    const label = svg
      .append('g')
      .selectAll('text')
      .data(data.nodes)
      .enter()
      .append('text')
      .text((d) => d.name.slice(0, 24))
      .attr('font-size', 10)
      .attr('dx', 12)
      .attr('dy', 4);

    simulation.on('tick', () => {
      link
        .attr('x1', (d: any) => d.source.x)
        .attr('y1', (d: any) => d.source.y)
        .attr('x2', (d: any) => d.target.x)
        .attr('y2', (d: any) => d.target.y);
      node.attr('cx', (d: any) => d.x).attr('cy', (d: any) => d.y);
      label.attr('x', (d: any) => d.x).attr('y', (d: any) => d.y);
    });

    return () => {
      simulation.stop();
    };
  }, [data, centerId]);

  if (data.nodes.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-ink-200 bg-white/60 p-6 text-center text-sm text-ink-500">
        No entity relationships on file. Run{' '}
        <code className="rounded bg-ink-100 px-1.5 py-0.5 text-xs">python scripts/graph.py build-all</code>{' '}
        to resolve officer and address links.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <svg ref={svgRef} style={{ width: '100%', height: 360 }} />
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-ink-500">
        <LegendDot color="#0ea5e9" label="Centered employer" />
        <LegendDot color="#dc2626" label="Violator" />
        <LegendDot color="#f97316" label="High score (50+)" />
        <LegendDot color="#eab308" label="Medium (25–49)" />
        <LegendDot color="#a3e635" label="Low / clean" />
      </div>
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className="inline-block h-2.5 w-2.5 rounded-full"
        style={{ backgroundColor: color }}
      />
      {label}
    </span>
  );
}

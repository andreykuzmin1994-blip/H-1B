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
          .distance(90),
      )
      .force('charge', d3.forceManyBody().strength(-240))
      .force('center', d3.forceCenter(width / 2, height / 2));

    const link = svg
      .append('g')
      .attr('stroke', '#8a867c')
      .attr('stroke-opacity', 0.5)
      .selectAll('line')
      .data(data.links)
      .enter()
      .append('line')
      .attr('stroke-width', (d) => 0.8 + d.confidence * 1.5);

    const node = svg
      .append('g')
      .selectAll('rect')
      .data(data.nodes)
      .enter()
      .append('rect')
      .attr('width', (d) => (d.id === centerId ? 14 : 9))
      .attr('height', (d) => (d.id === centerId ? 14 : 9))
      .attr('fill', (d) => {
        if (d.is_violator) return '#7a1616';
        if (d.id === centerId) return '#111111';
        if (d.anomaly_score >= 50) return '#b06427';
        if (d.anomaly_score >= 25) return '#9a8a26';
        return '#6a8a52';
      })
      .attr('stroke', '#111111')
      .attr('stroke-width', 0.5);

    node
      .append('title')
      .text((d) => `${d.name} (${d.state}) · score ${d.anomaly_score.toFixed(0)}`);

    const label = svg
      .append('g')
      .selectAll('text')
      .data(data.nodes)
      .enter()
      .append('text')
      .text((d) => d.name.slice(0, 28))
      .attr('font-size', 11)
      .attr('font-family', 'Source Serif 4, Georgia, serif')
      .attr('fill', '#111111')
      .attr('dx', 10)
      .attr('dy', 9);

    simulation.on('tick', () => {
      link
        .attr('x1', (d: any) => d.source.x)
        .attr('y1', (d: any) => d.source.y)
        .attr('x2', (d: any) => d.target.x)
        .attr('y2', (d: any) => d.target.y);
      node
        .attr('x', (d: any) => d.x - (d.id === centerId ? 7 : 4.5))
        .attr('y', (d: any) => d.y - (d.id === centerId ? 7 : 4.5));
      label.attr('x', (d: any) => d.x).attr('y', (d: any) => d.y);
    });

    return () => {
      simulation.stop();
    };
  }, [data, centerId]);

  if (data.nodes.length === 0) {
    return (
      <p className="text-sm italic text-ink-500">
        No entity relationships on file. Run{' '}
        <code className="font-mono text-xs">python scripts/graph.py build-all</code> to resolve
        officer and address links.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <svg ref={svgRef} style={{ width: '100%', height: 360 }} />
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1 text-[11px] uppercase tracking-wider text-ink-500">
        <Swatch color="#111111" label="Centered" />
        <Swatch color="#7a1616" label="Violator" />
        <Swatch color="#b06427" label="High" />
        <Swatch color="#9a8a26" label="Medium" />
        <Swatch color="#6a8a52" label="Low" />
      </div>
    </div>
  );
}

function Swatch({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-baseline gap-2">
      <span
        className="inline-block"
        style={{ width: 8, height: 8, backgroundColor: color }}
      />
      {label}
    </span>
  );
}

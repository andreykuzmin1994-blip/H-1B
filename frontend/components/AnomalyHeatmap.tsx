'use client';

import { useEffect, useRef } from 'react';
import * as d3 from 'd3';

interface Point {
  id: number;
  name: string;
  state: string | null;
  score: number;
  lat: number;
  lng: number;
}

export function AnomalyHeatmap({ points }: { points: Point[] }) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current) return;
    const width = 900;
    const height = 480;
    const svg = d3.select(svgRef.current).attr('viewBox', `0 0 ${width} ${height}`);
    svg.selectAll('*').remove();

    if (points.length === 0) {
      svg
        .append('text')
        .attr('x', width / 2)
        .attr('y', height / 2)
        .attr('text-anchor', 'middle')
        .attr('fill', '#8a867c')
        .attr('font-family', 'Source Serif 4, Georgia, serif')
        .attr('font-size', 16)
        .text('No geocoded employers yet.');
      return;
    }

    const projection = d3
      .geoAlbersUsa()
      .scale(1100)
      .translate([width / 2, height / 2]);

    const radius = d3
      .scaleSqrt()
      .domain([0, d3.max(points, (p) => p.score) ?? 100])
      .range([2, 16]);

    svg
      .append('g')
      .selectAll('circle')
      .data(points)
      .enter()
      .append('circle')
      .attr('cx', (p) => {
        const c = projection([p.lng, p.lat]);
        return c ? c[0] : -100;
      })
      .attr('cy', (p) => {
        const c = projection([p.lng, p.lat]);
        return c ? c[1] : -100;
      })
      .attr('r', (p) => radius(p.score))
      .attr('fill', (p) => {
        if (p.score >= 75) return '#7a1616';
        if (p.score >= 50) return '#b06427';
        if (p.score >= 25) return '#9a8a26';
        return '#6a8a52';
      })
      .attr('fill-opacity', 0.55)
      .attr('stroke', '#111111')
      .attr('stroke-width', 0.4)
      .on('click', (_evt, d) => {
        window.location.href = `/employer/${d.id}`;
      })
      .append('title')
      .text((p) => `${p.name} (${p.state}) · score ${p.score.toFixed(0)}`);
  }, [points]);

  return <svg ref={svgRef} style={{ width: '100%', height: 480 }} />;
}

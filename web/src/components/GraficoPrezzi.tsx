import { data as fData, eur } from "../lib/format";
import type { Prezzo } from "../lib/types";

/** Andamento del prezzo nel tempo (SVG semplice, a gradini). */
export default function GraficoPrezzi({ prezzi }: { prezzi: Prezzo[] }) {
  if (prezzi.length < 2 || prezzi.every((p) => p.prezzo === prezzi[0].prezzo)) {
    return <p className="text-sm text-slate-500">Prezzo invariato dalla prima rilevazione{prezzi[0] ? ` (${fData(prezzi[0].data)})` : ""}.</p>;
  }
  const W = 560, H = 140, P = 28;
  const t = prezzi.map((p) => new Date(p.data).getTime());
  const v = prezzi.map((p) => p.prezzo);
  const tMin = Math.min(...t), tMax = Math.max(...t, Date.now());
  const vMin = Math.min(...v) * 0.98, vMax = Math.max(...v) * 1.02;
  const x = (ti: number) => P + ((ti - tMin) / (tMax - tMin || 1)) * (W - 2 * P);
  const y = (vi: number) => H - P + -((vi - vMin) / (vMax - vMin || 1)) * (H - 2 * P);
  let d = `M${x(t[0])},${y(v[0])}`;
  for (let i = 1; i < v.length; i++) d += ` H${x(t[i])} V${y(v[i])}`;
  d += ` H${x(tMax)}`;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Andamento del prezzo">
      <line x1={P} x2={W - P} y1={H - P} y2={H - P} className="stroke-slate-200" />
      <path d={d} fill="none" className="stroke-brand-600" strokeWidth={2.5} />
      {prezzi.map((p, i) => (
        <g key={p.data}>
          <circle cx={x(t[i])} cy={y(v[i])} r={4} className="fill-white stroke-brand-600" strokeWidth={2} />
          <text x={x(t[i])} y={y(v[i]) - 9} textAnchor={i === 0 ? "start" : "middle"} className="fill-slate-700 text-[11px]">{eur(p.prezzo)}</text>
          <text x={x(t[i])} y={H - 10} textAnchor={i === 0 ? "start" : "middle"} className="fill-slate-400 text-[10px]">{fData(p.data)}</text>
        </g>
      ))}
    </svg>
  );
}

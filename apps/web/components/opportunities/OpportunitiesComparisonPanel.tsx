"use client";

import Link from "next/link";

import type { OpportunityRow } from "@/components/opportunities/OpportunitiesTable";

export function OpportunitiesComparisonPanel({
  rows,
}: {
  rows: OpportunityRow[];
}) {
  if (!rows.length) {
    return (
      <div className="rounded-[28px] border border-slate-800 bg-slate-900/70 p-6">
        <div className="text-xs uppercase tracking-[0.28em] text-slate-500">Comparison</div>
        <h2 className="mt-2 text-2xl font-semibold text-slate-100">Acquisition triage</h2>
        <p className="mt-3 text-sm leading-7 text-slate-400">
          Select two or more opportunities to compare their current recommendation, blockers,
          upside, and economics side by side.
        </p>
      </div>
    );
  }

  const rankedRows = [...rows].sort((left, right) => comparisonScore(right) - comparisonScore(left));
  const strongest = rankedRows[0] ?? null;
  const upsideLeader = [...rows].sort((left, right) => upsideScore(right) - upsideScore(left))[0] ?? null;

  return (
    <div className="rounded-[28px] border border-slate-800 bg-slate-900/70 p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-xs uppercase tracking-[0.28em] text-slate-500">Comparison</div>
          <h2 className="mt-2 text-2xl font-semibold text-slate-100">Parcel decision comparison</h2>
          <p className="mt-2 text-sm text-slate-400">
            {rows.length} selected parcels • ranked for acquisition triage, not just raw metrics
          </p>
        </div>
        {strongest ? (
          <div className="max-w-md rounded-2xl border border-emerald-400/30 bg-emerald-400/10 p-4 text-sm text-emerald-100">
            <div className="text-xs uppercase tracking-[0.18em] text-emerald-300">Strongest current buy</div>
            <div className="mt-2 font-semibold">{strongest.parcel_id}</div>
            <div className="mt-2 leading-6">{strongestWhy(strongest)}</div>
            {upsideLeader && upsideLeader.run_id !== strongest.run_id ? (
              <div className="mt-3 border-t border-emerald-400/20 pt-3 text-emerald-200">
                Best upside if constraints move: {upsideLeader.parcel_id} — {upsideLeader.upside_summary ?? "constraint relief could unlock additional value"}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      <div className="mt-6 grid gap-4 xl:grid-cols-3">
        {rankedRows.map((row) => {
          const best = row.run_id === strongest?.run_id;
          const bestUpside = row.run_id === upsideLeader?.run_id && row.near_feasible_flag;

          return (
            <article
              key={row.run_id}
              className={`rounded-[24px] border p-5 ${
                best
                  ? "border-emerald-400/40 bg-emerald-400/10"
                  : "border-slate-800 bg-slate-950/70"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-lg font-semibold text-slate-100">{row.parcel_id}</div>
                  <div className="mt-1 text-sm text-slate-400">{row.jurisdiction}</div>
                </div>
                <div className="flex flex-col items-end gap-2">
                  <DecisionBadge label={row.decision_label} />
                  <StatusBadge status={row.status} />
                  {best ? <Flag tone="best">Best current buy</Flag> : null}
                  {bestUpside ? <Flag tone="upside">Best upside</Flag> : null}
                </div>
              </div>

              <div className="mt-4 rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
                <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Why this parcel matters</div>
                <div className="mt-2 text-sm leading-6 text-slate-300">{triageSummary(row, best, bestUpside)}</div>
              </div>

              <div className="mt-4 grid grid-cols-2 gap-3">
                <Metric label="Units" value={formatInteger(row.units)} />
                <Metric label="ROI base" value={formatPercent(row.ROI_base)} />
                <Metric label="Projected profit" value={formatCurrency(row.projected_profit)} />
                <Metric label="Confidence" value={formatConfidence(row.confidence_score)} />
              </div>

              <div className="mt-4 space-y-4">
                <DetailBlock
                  label="Blockers"
                  value={row.blocker_summary ?? (row.near_feasible_flag ? "Constraint context exists but is not summarized." : "No explicit blocker reported.")}
                />
                <DetailBlock
                  label="Near-feasible upside"
                  value={row.upside_summary ?? (row.near_feasible_flag ? "Upside exists if the limiting constraint can be resolved." : "No near-feasible upside reported.")}
                  accent={Boolean(row.upside_summary)}
                />
                <DetailBlock
                  label="Major risk factors"
                  value={
                    row.key_risk_factors.length
                      ? row.key_risk_factors.slice(0, 3).join(", ")
                      : "No major risk factors were explicitly flagged."
                  }
                />
                <DetailBlock
                  label="Decision summary"
                  value={row.decision_summary}
                />
              </div>

              <div className="mt-5 flex gap-3">
                <Link
                  href={`/studio/${row.parcel_id}`}
                  className="rounded-xl border border-slate-700 px-3 py-2 text-sm font-semibold text-slate-200"
                >
                  Inspect parcel
                </Link>
                {row.has_run ? (
                  <Link
                    href={`/runs/${row.run_id}`}
                    className="rounded-xl border border-slate-700 px-3 py-2 text-sm font-semibold text-slate-200"
                  >
                    Open run
                  </Link>
                ) : null}
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-3">
      <div className="text-xs uppercase tracking-[0.18em] text-slate-500">{label}</div>
      <div className="mt-2 text-sm font-semibold text-slate-100">{value}</div>
    </div>
  );
}

function DetailBlock({
  label,
  value,
  accent = false,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div>
      <div className="text-xs uppercase tracking-[0.18em] text-slate-500">{label}</div>
      <div className={`mt-2 text-sm leading-6 ${accent ? "text-emerald-300" : "text-slate-300"}`}>{value}</div>
    </div>
  );
}

function Flag({ tone, children }: { tone: "best" | "upside"; children: React.ReactNode }) {
  const classes =
    tone === "best"
      ? "border-emerald-400/40 bg-emerald-400/10 text-emerald-300"
      : "border-cyan-400/40 bg-cyan-400/10 text-cyan-300";
  return <span className={`rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] ${classes}`}>{children}</span>;
}

function DecisionBadge({ label }: { label: OpportunityRow["decision_label"] }) {
  const tone =
    label === "BUY"
      ? "border-emerald-400/40 bg-emerald-400/10 text-emerald-300"
      : label === "CONDITIONAL"
        ? "border-amber-400/40 bg-amber-400/10 text-amber-300"
        : label === "PENDING"
          ? "border-slate-500/40 bg-slate-500/10 text-slate-300"
          : "border-rose-400/40 bg-rose-400/10 text-rose-300";
  return <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] ${tone}`}>{label}</span>;
}

function StatusBadge({ status }: { status: OpportunityRow["status"] }) {
  const tone =
    status === "completed"
      ? "border-emerald-400/40 bg-emerald-400/10 text-emerald-300"
      : status === "near_feasible"
        ? "border-amber-400/40 bg-amber-400/10 text-amber-300"
        : status === "loading"
          ? "border-slate-500/40 bg-slate-500/10 text-slate-300"
          : "border-rose-400/40 bg-rose-400/10 text-rose-300";
  return <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] ${tone}`}>{status.replace(/_/g, " ")}</span>;
}

function comparisonScore(row: OpportunityRow) {
  const decision =
    row.decision_label === "BUY" ? 4 : row.decision_label === "CONDITIONAL" ? 3 : row.decision_label === "PENDING" ? 2 : 1;
  const status = row.status === "completed" ? 3 : row.status === "near_feasible" ? 2 : row.status === "loading" ? 1 : 0;
  const roi = typeof row.ROI_base === "number" ? row.ROI_base : -1;
  const profit = typeof row.projected_profit === "number" ? row.projected_profit / 1_000_000 : -1;
  const confidence = typeof row.confidence_score === "number" ? row.confidence_score : 0;
  const riskPenalty = row.key_risk_factors.length * 0.1;
  return decision * 1000 + status * 100 + roi * 50 + profit * 10 + confidence - riskPenalty;
}

function upsideScore(row: OpportunityRow) {
  if (!row.near_feasible_flag) return -1;
  let score = 1;
  if (typeof row.ROI_best_case === "number") score += row.ROI_best_case * 100;
  if (typeof row.projected_profit === "number") score += row.projected_profit / 1_000_000;
  if (row.upside_summary) score += 5;
  return score;
}

function strongestWhy(row: OpportunityRow) {
  const parts: string[] = [];
  if (row.decision_label === "BUY") {
    parts.push("it is the strongest current buy recommendation");
  } else if (row.decision_label === "CONDITIONAL") {
    parts.push("it is the strongest conditional opportunity in the selected set");
  } else {
    parts.push("it still ranks highest among the selected parcels");
  }
  if (typeof row.ROI_base === "number") {
    parts.push(`base ROI ${formatPercent(row.ROI_base)}`);
  }
  if (typeof row.projected_profit === "number") {
    parts.push(`projected profit ${formatCurrency(row.projected_profit)}`);
  }
  if (typeof row.confidence_score === "number") {
    parts.push(`confidence ${formatConfidence(row.confidence_score)}`);
  }
  return capitalize(parts.join(" • "));
}

function triageSummary(row: OpportunityRow, best: boolean, bestUpside: boolean) {
  const parts: string[] = [];
  if (best) parts.push("Best current buy in this selected set.");
  if (bestUpside) parts.push("Strongest upside if constraints change.");
  parts.push(row.decision_summary);
  if (row.blocker_summary) {
    parts.push(`Blocker: ${row.blocker_summary}.`);
  }
  if (row.upside_summary) {
    parts.push(`Upside: ${row.upside_summary}.`);
  }
  return parts.join(" ");
}

function capitalize(value: string) {
  if (!value) return value;
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function formatCurrency(value: number | null | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPercent(value: number | null | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function formatConfidence(value: number | null | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return `${Math.round(value * 100)}%`;
}

function formatInteger(value: number | null | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return value.toLocaleString();
}

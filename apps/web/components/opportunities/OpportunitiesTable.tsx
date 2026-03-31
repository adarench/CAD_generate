"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import type { DealRecord, DealStatus } from "@/lib/opportunities";
import type { DecisionRecord } from "@/lib/parcels";

export type OpportunityRow = DealRecord;

type SortKey = "roi" | "projected_profit" | "confidence";

const SORT_OPTIONS: Array<{ value: SortKey; label: string }> = [
  { value: "roi", label: "ROI" },
  { value: "projected_profit", label: "Profit" },
  { value: "confidence", label: "Confidence" },
];

export function OpportunitiesTable({
  rows,
  decisionsByParcelId,
}: {
  rows: OpportunityRow[];
  decisionsByParcelId?: Map<string, DecisionRecord>;
}) {
  const router = useRouter();
  const [statusFilter, setStatusFilter] = useState<"all" | DealStatus>("all");
  const [jurisdictionFilter, setJurisdictionFilter] = useState("all");
  const [sortKey, setSortKey] = useState<SortKey>("roi");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");

  const jurisdictions = useMemo(
    () => Array.from(new Set(rows.map((row) => row.jurisdiction).filter(Boolean))).sort(),
    [rows]
  );

  const filteredRows = useMemo(() => {
    return rows.filter((row) => {
      if (statusFilter !== "all" && row.status !== statusFilter) return false;
      if (jurisdictionFilter !== "all" && row.jurisdiction !== jurisdictionFilter) return false;
      return true;
    });
  }, [jurisdictionFilter, rows, statusFilter]);

  const sortedRows = useMemo(() => {
    const direction = sortDirection === "asc" ? 1 : -1;
    return [...filteredRows].sort((left, right) => {
      const leftValue = sortValue(left, sortKey);
      const rightValue = sortValue(right, sortKey);
      if (leftValue === rightValue) {
        return right.last_run_at.localeCompare(left.last_run_at);
      }
      return (leftValue - rightValue) * direction;
    });
  }, [filteredRows, sortDirection, sortKey]);

  return (
    <div className="rounded-[28px] border border-slate-800 bg-slate-900/70 p-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-xs uppercase tracking-[0.28em] text-slate-500">Decision surface</div>
          <h2 className="mt-2 text-2xl font-semibold text-slate-100">Evaluated land deals</h2>
          <p className="mt-2 text-sm text-slate-400">
            {sortedRows.length} evaluated parcels — click a row to open the decision report
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <FilterSelect
            label="Status"
            value={statusFilter}
            onChange={(value) => setStatusFilter(value as "all" | DealStatus)}
            options={[
              { value: "all", label: "All statuses" },
              { value: "STRONG", label: "Strong" },
              { value: "MARGINAL", label: "Marginal" },
              { value: "PASS", label: "Pass" },
              { value: "NEAR_FEASIBLE", label: "Near feasible" },
            ]}
          />
          <FilterSelect
            label="Jurisdiction"
            value={jurisdictionFilter}
            onChange={setJurisdictionFilter}
            options={[
              { value: "all", label: "All jurisdictions" },
              ...jurisdictions.map((jurisdiction) => ({ value: jurisdiction, label: jurisdiction })),
            ]}
          />
          <FilterSelect
            label="Sort"
            value={sortKey}
            onChange={(value) => setSortKey(value as SortKey)}
            options={SORT_OPTIONS.map((option) => ({ value: option.value, label: option.label }))}
          />
          <FilterSelect
            label="Direction"
            value={sortDirection}
            onChange={(value) => setSortDirection(value as "asc" | "desc")}
            options={[
              { value: "desc", label: "High to low" },
              { value: "asc", label: "Low to high" },
            ]}
          />
        </div>
      </div>

      <div className="mt-6 overflow-x-auto">
        <table className="min-w-full border-separate border-spacing-y-3">
          <thead>
            <tr className="text-left text-xs uppercase tracking-[0.24em] text-slate-500">
              <th className="px-4 py-2">Parcel ID</th>
              <th className="px-4 py-2">Jurisdiction</th>
              <th className="px-4 py-2">Units</th>
              <th className="px-4 py-2">Projected Profit</th>
              <th className="px-4 py-2">ROI</th>
              <th className="px-4 py-2">Confidence</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2">Decision</th>
            </tr>
          </thead>
          <tbody>
            {sortedRows.map((row) => (
              <tr
                key={row.run_id}
                onClick={() => router.push(`/report/${row.parcel_id}`)}
                className="cursor-pointer rounded-2xl border border-slate-800 bg-slate-950/70 text-sm text-slate-300 transition hover:border-slate-600"
              >
                <td className="rounded-l-2xl px-4 py-4 align-top font-semibold text-slate-100">
                  <div>{row.parcel_id}</div>
                  <div className="mt-2 text-xs uppercase tracking-[0.16em] text-slate-500">
                    Run {formatTimestamp(row.last_run_at)}
                  </div>
                </td>
                <td className="px-4 py-4 align-top">{row.jurisdiction}</td>
                <td className="px-4 py-4 align-top">{formatInteger(row.units)}</td>
                <td className="px-4 py-4 align-top">{formatCurrency(row.projected_profit)}</td>
                <td className="px-4 py-4 align-top">{formatPercent(row.roi)}</td>
                <td className="px-4 py-4 align-top">{formatConfidence(row.confidence)}</td>
                <td className="px-4 py-4 align-top">
                  <div className="flex flex-col gap-2">
                    <StatusBadge status={row.status} />
                    <div className="text-xs uppercase tracking-[0.16em] text-slate-500">
                      {row.pipeline_status.replace(/_/g, " ")}
                    </div>
                    <Link
                      href={`/runs/${row.run_id}`}
                      onClick={(event) => event.stopPropagation()}
                      className="inline-flex text-xs uppercase tracking-[0.16em] text-cyan-300 hover:text-cyan-200"
                    >
                      Open run
                    </Link>
                  </div>
                </td>
                <td className="rounded-r-2xl px-4 py-4 align-top">
                  <DecisionCell decision={decisionsByParcelId?.get(row.parcel_id) ?? null} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!sortedRows.length ? (
        <div className="mt-4 rounded-2xl border border-dashed border-slate-700 px-4 py-8 text-sm text-slate-500">
          No evaluated deals match the current filters.
        </div>
      ) : null}
    </div>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
}) {
  return (
    <label className="flex flex-col gap-2 text-xs uppercase tracking-[0.2em] text-slate-500">
      <span>{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm font-medium normal-case tracking-normal text-slate-200"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function StatusBadge({ status }: { status: DealStatus }) {
  const tones: Record<DealStatus, string> = {
    STRONG: "border-emerald-400/40 bg-emerald-400/10 text-emerald-300",
    MARGINAL: "border-amber-400/40 bg-amber-400/10 text-amber-300",
    PASS: "border-rose-400/40 bg-rose-400/10 text-rose-300",
    NEAR_FEASIBLE: "border-violet-400/40 bg-violet-400/10 text-violet-300",
  };

  return (
    <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] ${tones[status]}`}>
      {status === "NEAR_FEASIBLE" ? "Near feasible" : status}
    </span>
  );
}

function sortValue(row: OpportunityRow, key: SortKey) {
  if (key === "confidence") {
    return row.confidence ?? -1;
  }
  return row[key];
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

function formatTimestamp(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function DecisionCell({ decision }: { decision: DecisionRecord | null }) {
  if (!decision) {
    return <span className="text-xs text-slate-600">—</span>;
  }
  const tones: Record<string, string> = {
    new: "border-slate-600 bg-slate-800 text-slate-300",
    in_review: "border-cyan-400/40 bg-cyan-400/10 text-cyan-300",
    decided: "border-emerald-400/40 bg-emerald-400/10 text-emerald-300",
    in_progress: "border-amber-400/40 bg-amber-400/10 text-amber-300",
    closed: "border-emerald-400/40 bg-emerald-400/10 text-emerald-300",
    abandoned: "border-rose-400/40 bg-rose-400/10 text-rose-300",
  };
  const tone = tones[decision.status] ?? tones.new;
  const label = decision.user_action
    ? decision.user_action.replace(/_/g, " ")
    : decision.status.replace(/_/g, " ");
  return (
    <span className={`inline-flex rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] ${tone}`}>
      {label}
    </span>
  );
}

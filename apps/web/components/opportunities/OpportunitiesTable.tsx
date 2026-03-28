"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import type { DecisionLabel, DecisionRecord } from "@/lib/opportunities";

export type OpportunityRow = DecisionRecord;

type SortKey = "ROI_base" | "projected_profit" | "confidence_score";

const SORT_OPTIONS: Array<{ value: SortKey; label: string }> = [
  { value: "ROI_base", label: "ROI" },
  { value: "projected_profit", label: "Profit" },
  { value: "confidence_score", label: "Confidence" },
];

export function OpportunitiesTable({
  rows,
  selectedRunIds,
  onSelectionChange,
}: {
  rows: OpportunityRow[];
  selectedRunIds: string[];
  onSelectionChange: (runIds: string[]) => void;
}) {
  const router = useRouter();
  const [statusFilter, setStatusFilter] = useState<"all" | OpportunityRow["status"]>("all");
  const [jurisdictionFilter, setJurisdictionFilter] = useState("all");
  const [sortKey, setSortKey] = useState<SortKey>("ROI_base");
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
      const leftDecision = decisionScore(left.decision_label);
      const rightDecision = decisionScore(right.decision_label);
      if (leftDecision !== rightDecision) {
        return (leftDecision - rightDecision) * direction;
      }
      const leftValue = sortValue(left, sortKey);
      const rightValue = sortValue(right, sortKey);
      if (leftValue === rightValue) {
        return right.last_run_at.localeCompare(left.last_run_at);
      }
      return (leftValue - rightValue) * direction;
    });
  }, [filteredRows, sortDirection, sortKey]);

  const allVisibleSelected =
    sortedRows.length > 0 && sortedRows.every((row) => selectedRunIds.includes(row.run_id));

  function toggleRow(runId: string) {
    onSelectionChange(
      selectedRunIds.includes(runId)
        ? selectedRunIds.filter((entry) => entry !== runId)
        : [...selectedRunIds, runId]
    );
  }

  function toggleVisibleRows() {
    if (allVisibleSelected) {
      onSelectionChange(
        selectedRunIds.filter((runId) => !sortedRows.some((row) => row.run_id === runId))
      );
      return;
    }
    const merged = new Set(selectedRunIds);
    for (const row of sortedRows) {
      merged.add(row.run_id);
    }
    onSelectionChange(Array.from(merged));
  }

  return (
    <div className="rounded-[28px] border border-slate-800 bg-slate-900/70 p-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-xs uppercase tracking-[0.28em] text-slate-500">Opportunities</div>
          <h2 className="mt-2 text-2xl font-semibold text-slate-100">Decision-ready parcel records</h2>
          <p className="mt-2 text-sm text-slate-400">
            {sortedRows.length} visible parcels • {selectedRunIds.length} selected
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <FilterSelect
            label="Status"
            value={statusFilter}
            onChange={(value) => setStatusFilter(value as "all" | OpportunityRow["status"])}
            options={[
              { value: "all", label: "All statuses" },
              { value: "completed", label: "Completed" },
              { value: "near_feasible", label: "Near feasible" },
              { value: "loading", label: "Loading" },
              { value: "failed", label: "Failed" },
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
              <th className="px-3">
                <input
                  type="checkbox"
                  aria-label="Select visible opportunities"
                  checked={allVisibleSelected}
                  onChange={toggleVisibleRows}
                  className="h-4 w-4 rounded border-slate-600 bg-slate-950 text-emerald-400"
                />
              </th>
              <th className="px-3 py-2">Decision</th>
              <th className="px-3 py-2">Confidence</th>
              <th className="px-3 py-2">Upside / blocker</th>
              <th className="px-3 py-2">Economics</th>
              <th className="px-3 py-2">Provenance</th>
            </tr>
          </thead>
          <tbody>
            {sortedRows.map((row) => {
              const selected = selectedRunIds.includes(row.run_id);
              return (
                <tr
                  key={row.run_id}
                  onClick={() => router.push(`/studio/${row.parcel_id}`)}
                  className={`cursor-pointer rounded-2xl border text-sm text-slate-300 transition ${
                    selected
                      ? "border-emerald-400/40 bg-emerald-400/10"
                      : "border-slate-800 bg-slate-950/70 hover:border-slate-600"
                  }`}
                >
                  <td className="rounded-l-2xl px-3 py-4 align-top" onClick={(event) => event.stopPropagation()}>
                    <input
                      type="checkbox"
                      aria-label={`Select ${row.parcel_id}`}
                      checked={selected}
                      onChange={() => toggleRow(row.run_id)}
                      className="h-4 w-4 rounded border-slate-600 bg-slate-950 text-emerald-400"
                    />
                  </td>
                  <td className="px-3 py-4 align-top">
                    <div className="flex flex-col gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <DecisionBadge label={row.decision_label} />
                        <StatusBadge status={row.status} />
                      </div>
                      <div className="font-semibold text-slate-100">{row.parcel_id}</div>
                      <div className="text-sm text-slate-400">{row.jurisdiction}</div>
                      <div className="max-w-sm text-sm leading-6 text-slate-300">
                        {row.decision_summary}
                      </div>
                    </div>
                  </td>
                  <td className="px-3 py-4 align-top">
                    <div className="font-semibold text-slate-100">
                      {formatConfidence(row.confidence_score)}
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {row.key_risk_factors.length ? (
                        row.key_risk_factors.slice(0, 3).map((factor) => (
                          <span
                            key={factor}
                            className="rounded-full border border-slate-700 px-3 py-1 text-xs text-slate-300"
                          >
                            {factor}
                          </span>
                        ))
                      ) : (
                        <span className="text-sm text-slate-500">No explicit risk factors.</span>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-4 align-top">
                    <div className="text-sm leading-6 text-slate-300">
                      {row.blocker_summary ??
                        row.near_feasible_summary ??
                        (row.near_feasible_flag
                          ? "Near-feasible details unavailable."
                          : "No material blocker reported.")}
                    </div>
                    {row.upside_summary ? (
                      <div className="mt-2 text-sm text-emerald-300">{row.upside_summary}</div>
                    ) : null}
                    <div className="mt-2 text-xs uppercase tracking-[0.18em] text-slate-500">
                      {row.near_feasible_flag ? "Constraint-sensitive upside" : "Current blocker view"}
                    </div>
                  </td>
                  <td className="px-3 py-4 align-top">
                    <div className="grid gap-1 text-sm text-slate-300">
                      <div>
                        Units: <span className="font-semibold text-slate-100">{formatInteger(row.units)}</span>
                      </div>
                      <div>
                        ROI: <span className="font-semibold text-slate-100">{formatPercent(row.ROI_base)}</span>
                      </div>
                      <div>
                        Profit: <span className="font-semibold text-slate-100">{formatCurrency(row.projected_profit)}</span>
                      </div>
                    </div>
                    <div className="mt-2 text-xs text-slate-500">
                      Range: {formatRange(row.ROI_worst_case, row.ROI_best_case)}
                    </div>
                  </td>
                  <td className="rounded-r-2xl px-3 py-4 align-top">
                    <div className="max-w-sm text-sm leading-6 text-slate-300">{row.provenance_summary}</div>
                    <div className="mt-2 text-xs text-slate-500">
                      Last run: {formatTimestamp(row.last_run_at)}
                    </div>
                    {row.has_run ? (
                      <Link
                        href={`/runs/${row.run_id}`}
                        onClick={(event) => event.stopPropagation()}
                        className="mt-3 inline-flex text-xs uppercase tracking-[0.18em] text-cyan-300 hover:text-cyan-200"
                      >
                        Open run
                      </Link>
                    ) : (
                      <div className="mt-3 text-xs uppercase tracking-[0.18em] text-slate-500">
                        Evaluating
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {!sortedRows.length ? (
        <div className="mt-4 rounded-2xl border border-dashed border-slate-700 px-4 py-8 text-sm text-slate-500">
          No opportunities match the current filters.
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

function DecisionBadge({ label }: { label: DecisionLabel }) {
  const tone =
    label === "BUY"
      ? "border-emerald-400/40 bg-emerald-400/10 text-emerald-300"
      : label === "CONDITIONAL"
        ? "border-amber-400/40 bg-amber-400/10 text-amber-300"
        : label === "PENDING"
          ? "border-slate-500/40 bg-slate-500/10 text-slate-300"
          : "border-rose-400/40 bg-rose-400/10 text-rose-300";

  return (
    <span
      className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] ${tone}`}
    >
      {label}
    </span>
  );
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

  return (
    <span
      className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] ${tone}`}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}

function sortValue(row: OpportunityRow, sortKey: SortKey) {
  const value = row[sortKey];
  if (typeof value !== "number" || Number.isNaN(value)) {
    return Number.NEGATIVE_INFINITY;
  }
  return value;
}

function decisionScore(label: DecisionLabel) {
  return label === "BUY" ? 4 : label === "CONDITIONAL" ? 3 : label === "PENDING" ? 2 : 1;
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

function formatRange(low: number | null | undefined, high: number | null | undefined) {
  if (typeof low !== "number" || typeof high !== "number") return "—";
  return `${formatPercent(low)} to ${formatPercent(high)}`;
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
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) return value;
  return timestamp.toLocaleString();
}

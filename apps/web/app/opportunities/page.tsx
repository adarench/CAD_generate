"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";

import { OpportunitiesTable } from "@/components/opportunities/OpportunitiesTable";
import { fetchDecisions, fetchRun, fetchRuns } from "@/lib/api";
import { dealRecordFromPipelineRun, type DealRecord } from "@/lib/opportunities";
import type { DecisionRecord, PipelineRun } from "@/lib/parcels";
import { useShortlist } from "@/lib/shortlist";

export default function OpportunitiesPage() {
  const shortlist = useShortlist();
  const runsQuery = useQuery({
    queryKey: ["opportunities", "runs"],
    queryFn: () => fetchRuns({ limit: 120, sort: "timestamp", order: "desc" }),
  });

  const detailQueries = useQueries({
    queries: (runsQuery.data ?? []).map((summary) => ({
      queryKey: ["opportunities", "run", summary.run_id],
      queryFn: () => fetchRun(summary.run_id),
      retry: false,
      staleTime: 30_000,
    })),
  });

  const dealRows = useMemo(() => {
    const latestByParcelId = new Map<string, DealRecord>();

    for (const run of detailQueries.map((query) => query.data).filter((value): value is PipelineRun => Boolean(value))) {
      const deal = dealRecordFromPipelineRun(run);
      if (!deal) continue;
      const existing = latestByParcelId.get(deal.parcel_id);
      if (!existing || deal.last_run_at > existing.last_run_at) {
        latestByParcelId.set(deal.parcel_id, deal);
      }
    }

    return Array.from(latestByParcelId.values());
  }, [detailQueries]);

  const dealsByParcelId = useMemo(
    () => new Map(dealRows.map((row) => [row.parcel_id, row])),
    [dealRows]
  );

  const visibleRows = useMemo(() => {
    if (!shortlist.shortlistIds.length) {
      return dealRows;
    }
    return shortlist.shortlistIds
      .map((parcelId) => dealsByParcelId.get(parcelId) ?? null)
      .filter((row): row is DealRecord => Boolean(row));
  }, [dealRows, dealsByParcelId, shortlist.shortlistIds]);

  const pendingShortlistCount = useMemo(() => {
    if (!shortlist.shortlistIds.length) return 0;
    return shortlist.shortlistIds.filter((parcelId) => !dealsByParcelId.has(parcelId)).length;
  }, [dealsByParcelId, shortlist.shortlistIds]);

  const decisionsQuery = useQuery({
    queryKey: ["decisions"],
    queryFn: () => fetchDecisions({ limit: 200 }),
  });
  const decisionsByParcelId = useMemo(() => {
    const map = new Map<string, DecisionRecord>();
    for (const d of decisionsQuery.data ?? []) {
      if (!map.has(d.parcel_id)) map.set(d.parcel_id, d);
    }
    return map;
  }, [decisionsQuery.data]);

  const isLoadingRuns = runsQuery.isLoading || detailQueries.some((query) => query.isLoading);
  const firstDetailError = detailQueries.find((query) => query.error instanceof Error)?.error ?? null;
  const hasError = runsQuery.isError || detailQueries.some((query) => query.isError);
  const errorMessage =
    runsQuery.error instanceof Error
      ? runsQuery.error.message
      : firstDetailError instanceof Error
        ? firstDetailError.message
        : "Failed to load evaluated deals.";

  return (
    <div className="px-6 py-8">
      <div className="mx-auto max-w-[1600px]">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-[0.32em] text-slate-500">Decision surface</div>
            <h1 className="mt-2 text-3xl font-semibold text-slate-100">
              Opportunities are evaluated deals, not map hits
            </h1>
            <p className="mt-3 max-w-4xl text-sm leading-7 text-slate-400">
              This surface only shows parcels with persisted feasibility output. Discovery selects land.
              Opportunities decides what to buy. Studio is where you inspect a single evaluated parcel.
            </p>
          </div>
          <div className="flex gap-3">
            <Link
              href="/map"
              className="rounded-2xl border border-slate-700 px-4 py-2 text-sm font-semibold text-slate-200"
            >
              Go to Discovery
            </Link>
          </div>
        </div>

        {shortlist.shortlistIds.length ? (
          <div className="mt-8 rounded-[28px] border border-slate-800 bg-slate-900/70 p-6">
            <div className="text-xs uppercase tracking-[0.28em] text-slate-500">Shortlist pipeline</div>
            <div className="mt-2 text-sm leading-7 text-slate-300">
              {visibleRows.length} shortlisted parcels already have saved feasibility results.
              {pendingShortlistCount
                ? ` ${pendingShortlistCount} shortlisted parcels are still waiting for evaluation and will not appear here until a run is saved.`
                : " Every shortlisted parcel with a saved run is now eligible for decision review."}
            </div>
          </div>
        ) : null}

        {isLoadingRuns ? (
          <LoadingPanel message="Loading evaluated deals…" />
        ) : hasError ? (
          <LoadingPanel message={errorMessage} />
        ) : !visibleRows.length ? (
          <EmptyState pendingShortlistCount={pendingShortlistCount} />
        ) : (
          <div className="mt-8">
            <OpportunitiesTable rows={visibleRows} decisionsByParcelId={decisionsByParcelId} />
          </div>
        )}
      </div>
    </div>
  );
}

function LoadingPanel({ message }: { message: string }) {
  return (
    <div className="mt-8 rounded-[28px] border border-slate-800 bg-slate-900/70 p-8 text-sm text-slate-400">
      {message}
    </div>
  );
}

function EmptyState({ pendingShortlistCount }: { pendingShortlistCount: number }) {
  return (
    <div className="mt-8 rounded-[28px] border border-dashed border-slate-700 bg-slate-900/70 p-10">
      <div className="text-xs uppercase tracking-[0.28em] text-slate-500">No opportunities yet</div>
      <h2 className="mt-3 text-2xl font-semibold text-slate-100">
        You have not evaluated any parcels yet.
      </h2>
      <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-400">
        Go to Discovery to select a parcel and run feasibility.
        {pendingShortlistCount
          ? ` ${pendingShortlistCount} shortlisted parcels are still waiting on saved feasibility results.`
          : ""}
      </p>
      <Link
        href="/map"
        className="mt-6 inline-flex rounded-2xl bg-cyan-400 px-5 py-3 text-sm font-semibold uppercase tracking-[0.22em] text-slate-950 shadow-lg shadow-cyan-500/20 transition hover:bg-cyan-300"
      >
        Open Discovery
      </Link>
    </div>
  );
}

"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";

import { OpportunitiesComparisonPanel } from "@/components/opportunities/OpportunitiesComparisonPanel";
import { OpportunitiesTable, type OpportunityRow } from "@/components/opportunities/OpportunitiesTable";
import {
  ensureBedrockParcel,
  fetchDiscoveryParcel,
  fetchRun,
  fetchRuns,
  runBedrockPipeline,
} from "@/lib/api";
import { decisionRecordFromPipelineRun, placeholderDecisionRecord } from "@/lib/opportunities";
import type { PipelineRun } from "@/lib/parcels";
import { useShortlist } from "@/lib/shortlist";

export default function OpportunitiesPage() {
  const shortlist = useShortlist();
  const [selectedRunIds, setSelectedRunIds] = useState<string[]>([]);
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

  const runRows = useMemo(() => {
    return detailQueries
      .map((query) => query.data)
      .filter((run): run is PipelineRun => Boolean(run))
      .map(decisionRecordFromPipelineRun);
  }, [detailQueries]);

  const latestRunByParcelId = useMemo(() => {
    const map = new Map<string, OpportunityRow>();
    for (const row of runRows) {
      const existing = map.get(row.parcel_id);
      if (!existing || row.last_run_at > existing.last_run_at) {
        map.set(row.parcel_id, row);
      }
    }
    return map;
  }, [runRows]);

  const shortlistParcelQueries = useQueries({
    queries: shortlist.shortlistIds.map((parcelId) => ({
      queryKey: ["opportunities", "shortlist", "parcel", parcelId],
      queryFn: () => fetchDiscoveryParcel(parcelId),
      retry: false,
      staleTime: 30_000,
      enabled: !latestRunByParcelId.has(parcelId),
    })),
  });

  const shortlistPipelineQueries = useQueries({
    queries: shortlist.shortlistIds.map((parcelId) => ({
      queryKey: ["opportunities", "shortlist", "pipeline", parcelId],
      queryFn: async () => {
        const parcel = await ensureBedrockParcel(parcelId);
        return runBedrockPipeline(parcel);
      },
      retry: false,
      staleTime: 0,
      enabled: !latestRunByParcelId.has(parcelId),
    })),
  });

  const visibleRows = useMemo(() => {
    if (!shortlist.shortlistIds.length) {
      return runRows;
    }
    return shortlist.shortlistIds.map((parcelId, index) => {
      const existingRow = latestRunByParcelId.get(parcelId);
      if (existingRow) {
        return existingRow;
      }

      const pipelineQuery = shortlistPipelineQueries[index];
      if (pipelineQuery?.data) {
        return decisionRecordFromPipelineRun(pipelineQuery.data);
      }

      const parcelQuery = shortlistParcelQueries[index];
      return placeholderDecisionRecord(parcelId, parcelQuery?.data, pipelineQuery?.error);
    });
  }, [latestRunByParcelId, runRows, shortlist.shortlistIds, shortlistParcelQueries, shortlistPipelineQueries]);

  const selectedRows = useMemo(
    () => visibleRows.filter((row) => selectedRunIds.includes(row.run_id)),
    [selectedRunIds, visibleRows]
  );

  return (
    <div className="px-6 py-8">
      <div className="mx-auto max-w-[1600px]">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-[0.32em] text-slate-500">Primary surface</div>
            <h1 className="mt-2 text-3xl font-semibold text-slate-100">
              Decision records from live pipeline output
            </h1>
            <p className="mt-3 max-w-4xl text-sm leading-7 text-slate-400">
              Screen shortlisted parcels by acquisition decision, confidence, blocker, and economics.
              Compare here, then inspect the strongest candidates in the parcel decision view.
            </p>
          </div>
          <div className="flex gap-3">
            <Link
              href="/map"
              className="rounded-2xl border border-slate-700 px-4 py-2 text-sm font-semibold text-slate-200"
            >
              Open discovery map
            </Link>
            <Link
              href="/map"
              className="rounded-2xl border border-slate-700 px-4 py-2 text-sm font-semibold text-slate-200"
            >
              Back to discovery
            </Link>
          </div>
        </div>

        {runsQuery.isLoading ? (
          <LoadingPanel message="Loading pipeline opportunities…" />
        ) : runsQuery.isError ? (
          <LoadingPanel
            message={runsQuery.error instanceof Error ? runsQuery.error.message : "Failed to load opportunities."}
          />
        ) : (
          <div className="mt-8 grid gap-8">
            <div className="rounded-[28px] border border-slate-800 bg-slate-900/70 p-6">
              <div className="text-xs uppercase tracking-[0.28em] text-slate-500">Shortlist scope</div>
              <div className="mt-2 text-sm text-slate-300">
                {shortlist.shortlistIds.length
                  ? `${shortlist.shortlistIds.length} shortlisted parcels are driving this decision table.`
                  : "No shortlist is active, so all available decision records are visible."}
              </div>
            </div>
            <OpportunitiesComparisonPanel rows={selectedRows} />
            <OpportunitiesTable
              rows={visibleRows}
              selectedRunIds={selectedRunIds}
              onSelectionChange={setSelectedRunIds}
            />
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

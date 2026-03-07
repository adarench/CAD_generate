"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { fetchRecentRuns } from "@/lib/api";

export default function RunsPage() {
  const runsQuery = useQuery({
    queryKey: ["runs-page"],
    queryFn: () => fetchRecentRuns(20),
  });

  return (
    <div className="px-6 py-8">
      <div className="mx-auto max-w-[1400px]">
        <div className="flex items-end justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-[0.32em] text-slate-500">Saved runs</div>
            <h1 className="mt-2 text-3xl font-semibold text-slate-100">
              Optimization history and saved concept plans
            </h1>
          </div>
          <Link
            href="/map"
            className="rounded-2xl border border-slate-700 px-4 py-2 text-sm font-semibold text-slate-200"
          >
            Open parcel map
          </Link>
        </div>

        <div className="mt-8 rounded-[28px] border border-slate-800 bg-slate-900/70 p-6">
          <div className="grid grid-cols-[1.4fr_1fr_1fr_1fr_0.9fr] gap-3 px-4 text-xs uppercase tracking-[0.24em] text-slate-500">
            <span>Parcel</span>
            <span>County</span>
            <span>Winning topology</span>
            <span>Lots</span>
            <span>Status</span>
          </div>
          <div className="mt-4 space-y-3">
            {(runsQuery.data ?? []).map((run) => (
              <Link
                key={run.runId}
                href={`/runs/${run.runId}`}
                className="grid grid-cols-[1.4fr_1fr_1fr_1fr_0.9fr] gap-3 rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-4 text-sm text-slate-300 transition hover:border-slate-600"
              >
                <span className="font-semibold text-slate-100">{run.parcelApn ?? run.parcelId}</span>
                <span>{run.county ?? "—"}</span>
                <span className="capitalize">{run.winningTopology}</span>
                <span>{run.lotCount}</span>
                <span className="capitalize">{run.status}</span>
              </Link>
            ))}
            {!runsQuery.data?.length ? (
              <div className="rounded-2xl border border-dashed border-slate-700 px-4 py-8 text-sm text-slate-500">
                No saved runs yet. Generate a concept plan from the parcel map to seed history.
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

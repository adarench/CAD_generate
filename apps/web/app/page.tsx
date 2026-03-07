"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchRecentParcels, fetchRecentRuns, searchParcelByApn } from "@/lib/api";
import { SUPPORTED_UTAH_COUNTIES } from "@/services/parcels/arcgisParcelClient";

const counties = [...SUPPORTED_UTAH_COUNTIES];

export default function HomePage() {
  const recentParcels = useQuery({
    queryKey: ["recent-parcels"],
    queryFn: () => fetchRecentParcels(4),
  });
  const recentRuns = useQuery({
    queryKey: ["recent-runs"],
    queryFn: () => fetchRecentRuns(5),
  });
  const [county, setCounty] = useState<string>(counties[0]);
  const [apn, setApn] = useState("");
  const [apnResult, setApnResult] = useState<string | null>(null);
  const [apnError, setApnError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);

  async function handleQuickSearch() {
    setSearching(true);
    setApnError(null);
    try {
      const matches = await searchParcelByApn(county, apn);
      setApnResult(matches[0]?.id ?? null);
      if (!matches.length) {
        setApnError("No parcel matched that county/APN combination.");
      }
    } catch (error) {
      setApnError(error instanceof Error ? error.message : "APN lookup failed.");
    } finally {
      setSearching(false);
    }
  }

  return (
    <section className="px-6 py-10">
      <div className="mx-auto grid max-w-[1600px] gap-8 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="rounded-[32px] border border-slate-800 bg-slate-900/70 p-10 shadow-2xl shadow-slate-950/50">
          <div className="inline-flex rounded-full border border-emerald-400/30 bg-emerald-400/10 px-4 py-1 text-xs font-semibold uppercase tracking-[0.28em] text-emerald-300">
            Utah-first land feasibility
          </div>
          <h1 className="mt-6 max-w-4xl text-5xl font-semibold leading-tight text-slate-50">
            Select a real parcel, run topology-aware subdivision yield, and review a concept plan
            in one workspace.
          </h1>
          <p className="mt-5 max-w-3xl text-lg leading-8 text-slate-300">
            Utah Subdivision Studio connects live parcel retrieval, normalized land records,
            street-network optimization, and export-ready concept geometry for acquisition and
            early planning teams.
          </p>
          <div className="mt-8 flex flex-wrap gap-4">
            <Link
              href="/map"
              className="rounded-2xl bg-emerald-400 px-6 py-3 text-sm font-semibold uppercase tracking-[0.22em] text-slate-950 shadow-lg shadow-emerald-500/20 transition hover:bg-emerald-300"
            >
              Open parcel map
            </Link>
            <Link
              href="/runs"
              className="rounded-2xl border border-slate-700 px-6 py-3 text-sm font-semibold uppercase tracking-[0.22em] text-slate-200 transition hover:border-slate-500"
            >
              View saved runs
            </Link>
          </div>

          <div className="mt-10 rounded-[28px] border border-slate-800 bg-slate-950/70 p-6">
            <div className="text-xs uppercase tracking-[0.3em] text-slate-500">Quick APN lookup</div>
            <div className="mt-4 flex gap-3">
              <select
                className="rounded-2xl border border-slate-700 bg-slate-900 px-4 py-3 text-sm text-slate-200"
                value={county}
                onChange={(event) => setCounty(event.target.value)}
              >
                {counties.map((entry) => (
                  <option key={entry} value={entry}>
                    {entry} County
                  </option>
                ))}
              </select>
              <input
                className="flex-1 rounded-2xl border border-slate-700 bg-slate-900 px-4 py-3 text-sm text-slate-100"
                placeholder="Enter county-scoped APN"
                value={apn}
                onChange={(event) => setApn(event.target.value)}
              />
              <button
                className="rounded-2xl bg-slate-100 px-5 py-3 text-sm font-semibold text-slate-950 disabled:opacity-50"
                onClick={handleQuickSearch}
                disabled={searching || !apn.trim()}
              >
                {searching ? "Searching..." : "Find"}
              </button>
            </div>
            {apnResult ? (
              <Link
                href={`/planner/${apnResult}`}
                className="mt-4 inline-flex rounded-xl border border-emerald-400/40 px-4 py-2 text-sm font-semibold text-emerald-300"
              >
                Open concept planner
              </Link>
            ) : null}
            {apnError ? <p className="mt-4 text-sm text-red-300">{apnError}</p> : null}
          </div>
        </div>

        <div className="grid gap-6">
          <ActivityCard
            title="Recent parcels"
            subtitle="Cached parcel records ready for planning"
            emptyText="Parcel history will appear after your first live lookup."
            items={(recentParcels.data ?? []).map((parcel) => ({
              id: parcel.id,
              title: parcel.apn ?? parcel.id,
              detail: `${parcel.county} County • ${parcel.areaAcres?.toFixed(2) ?? "—"} acres`,
              href: `/planner/${parcel.id}`,
            }))}
          />
          <ActivityCard
            title="Recent runs"
            subtitle="Saved concept-plan results and exports"
            emptyText="Saved runs will appear once optimization is executed."
            items={(recentRuns.data ?? []).map((run) => ({
              id: run.runId,
              title: `${run.winningTopology} • ${run.lotCount} lots`,
              detail: `${run.county ?? "UT"} • ${run.parcelApn ?? run.parcelId}`,
              href: `/runs/${run.runId}`,
            }))}
          />
        </div>
      </div>
    </section>
  );
}

function ActivityCard({
  title,
  subtitle,
  emptyText,
  items,
}: {
  title: string;
  subtitle: string;
  emptyText: string;
  items: { id: string; title: string; detail: string; href: string }[];
}) {
  return (
    <div className="rounded-[28px] border border-slate-800 bg-slate-900/70 p-6">
      <div className="text-xs uppercase tracking-[0.3em] text-slate-500">{title}</div>
      <div className="mt-2 text-sm text-slate-400">{subtitle}</div>
      <div className="mt-5 space-y-3">
        {items.length ? (
          items.map((item) => (
            <Link
              key={item.id}
              href={item.href}
              className="block rounded-2xl border border-slate-800 bg-slate-950/70 p-4 transition hover:border-slate-600"
            >
              <div className="font-semibold text-slate-100">{item.title}</div>
              <div className="mt-1 text-sm text-slate-400">{item.detail}</div>
            </Link>
          ))
        ) : (
          <div className="rounded-2xl border border-dashed border-slate-700 px-4 py-6 text-sm text-slate-500">
            {emptyText}
          </div>
        )}
      </div>
    </div>
  );
}

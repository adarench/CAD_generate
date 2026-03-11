"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchRecentParcels, fetchRecentRuns, searchParcelByApn } from "@/lib/api";
import { DEFAULT_MAP_COUNTY, DEFAULT_STUDIO_DEMO_APN, DEFAULT_STUDIO_DEMO_PARCEL_ID } from "@/lib/mapConfig";
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
  const [county, setCounty] = useState<string>(DEFAULT_MAP_COUNTY);
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
      <div className="mx-auto max-w-[1600px]">
        <div className="rounded-[36px] border border-slate-800 bg-slate-900/75 p-10 shadow-2xl shadow-slate-950/50">
          <div className="inline-flex rounded-full border border-cyan-400/30 bg-cyan-400/10 px-4 py-1 text-xs font-semibold uppercase tracking-[0.28em] text-cyan-300">
            Discovery + Studio
          </div>
          <h1 className="mt-6 max-w-5xl text-5xl font-semibold leading-tight text-slate-50">
            A two-surface land feasibility product: parcel discovery on GIS, concept generation in a
            dedicated planning Studio.
          </h1>
          <p className="mt-5 max-w-4xl text-lg leading-8 text-slate-300">
            Utah Subdivision Studio separates parcel intake from design work. Use the GIS Discovery layer
            to find and inspect real parcels, then open a CAD-style Studio workspace for prompt-first
            subdivision feasibility and export-ready geometry.
          </p>
          <div className="mt-8 flex flex-wrap gap-4">
            <Link
              href="/map"
              className="rounded-2xl bg-cyan-400 px-6 py-3 text-sm font-semibold uppercase tracking-[0.22em] text-slate-950 shadow-lg shadow-cyan-500/20 transition hover:bg-cyan-300"
            >
              Open discovery map
            </Link>
            <Link
              href={`/studio/${DEFAULT_STUDIO_DEMO_PARCEL_ID}`}
              className="rounded-2xl border border-cyan-400/40 px-6 py-3 text-sm font-semibold uppercase tracking-[0.22em] text-cyan-300 transition hover:border-cyan-300"
            >
              Open Studio demo parcel
            </Link>
            <Link
              href="/runs"
              className="rounded-2xl border border-slate-700 px-6 py-3 text-sm font-semibold uppercase tracking-[0.22em] text-slate-200 transition hover:border-slate-500"
            >
              View saved runs
            </Link>
          </div>
        </div>

        <div className="mt-8 grid gap-8 xl:grid-cols-[1.15fr_0.85fr]">
          <div className="grid gap-6">
            <div className="grid gap-6 lg:grid-cols-2">
              <SurfaceCard
                eyebrow="Surface A"
                title="GIS Discovery"
                description="Browse parcel polygons on a live GIS map, search by county + APN, inspect parcel metadata, and launch the selected parcel into Studio."
                bullets={[
                  "Visible parcel polygons",
                  "County + APN lookup",
                  "Map click selection",
                  "Parcel detail drawer",
                ]}
                href="/map"
                cta="Open Discovery"
              />
              <SurfaceCard
                eyebrow="Surface B"
                title="Studio Workspace"
                description="Load a normalized parcel into a CAD-style design canvas, enter a concept prompt, adjust optional parameters, run optimization, and export geometry."
                bullets={[
                  "Prompt-first design input",
                  "Parameter-assisted controls",
                  "CAD-style geometry canvas",
                  "DXF / STEP / GeoJSON exports",
                ]}
                href={apnResult ? `/studio/${apnResult}` : `/studio/${DEFAULT_STUDIO_DEMO_PARCEL_ID}`}
                cta={apnResult ? "Open Studio" : "Open Studio Demo"}
              />
            </div>

            <div className="rounded-[30px] border border-slate-800 bg-slate-900/70 p-6">
              <div className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-500">
                Quick Studio launch
              </div>
              <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-400">
                Use APN lookup to jump directly into the Studio route for a normalized parcel record.
              </p>
              <div className="mt-4 rounded-2xl border border-cyan-400/20 bg-cyan-400/10 px-4 py-3 text-sm text-cyan-100">
                Demo parcel ready: {DEFAULT_STUDIO_DEMO_APN} in Salt Lake County with prior high-yield Studio runs.
              </div>
              <div className="mt-4 flex flex-wrap gap-3">
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
                  className="min-w-[260px] flex-1 rounded-2xl border border-slate-700 bg-slate-900 px-4 py-3 text-sm text-slate-100"
                  placeholder="Enter county-scoped APN"
                  value={apn}
                  onChange={(event) => setApn(event.target.value)}
                />
                <button
                  className="rounded-2xl bg-slate-100 px-5 py-3 text-sm font-semibold text-slate-950 disabled:opacity-50"
                  onClick={handleQuickSearch}
                  disabled={searching || !apn.trim()}
                >
                  {searching ? "Searching..." : "Find parcel"}
                </button>
              </div>
              <div className="mt-4 flex flex-wrap gap-3">
                {apnResult ? (
                  <Link
                    href={`/studio/${apnResult}`}
                    className="inline-flex rounded-xl border border-cyan-400/40 px-4 py-2 text-sm font-semibold text-cyan-300"
                  >
                    Open parcel in Studio
                  </Link>
                ) : null}
                <Link
                  href={`/studio/${DEFAULT_STUDIO_DEMO_PARCEL_ID}`}
                  className="inline-flex rounded-xl border border-slate-700 px-4 py-2 text-sm font-semibold text-slate-200"
                >
                  Open demo parcel
                </Link>
              </div>
              {apnError ? <p className="mt-4 text-sm text-red-300">{apnError}</p> : null}
            </div>
          </div>

          <div className="grid gap-6">
            <ActivityCard
              title="Recent parcels"
              subtitle="Normalized parcel records ready for Studio"
              emptyText="Parcel history will appear after live discovery lookups."
              items={(recentParcels.data ?? []).map((parcel) => ({
                id: parcel.id,
                title: parcel.apn ?? parcel.id,
                detail: `${parcel.county} County • ${parcel.areaAcres?.toFixed(2) ?? "—"} acres`,
                href: `/studio/${parcel.id}`,
              }))}
            />
            <ActivityCard
              title="Recent runs"
              subtitle="Saved concept plans and exports"
              emptyText="Saved runs will appear after Studio generation."
              items={(recentRuns.data ?? []).map((run) => ({
                id: run.runId,
                title: `${run.winningTopology} • ${run.lotCount} lots`,
                detail: `${run.county ?? "UT"} • ${run.parcelApn ?? run.parcelId}`,
                href: `/runs/${run.runId}`,
              }))}
            />
          </div>
        </div>
      </div>
    </section>
  );
}

function SurfaceCard({
  eyebrow,
  title,
  description,
  bullets,
  href,
  cta,
  disabled = false,
}: {
  eyebrow: string;
  title: string;
  description: string;
  bullets: string[];
  href: string;
  cta: string;
  disabled?: boolean;
}) {
  return (
    <div className="rounded-[30px] border border-slate-800 bg-slate-900/70 p-6">
      <div className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-500">{eyebrow}</div>
      <h2 className="mt-2 text-2xl font-semibold text-slate-50">{title}</h2>
      <p className="mt-3 text-sm leading-7 text-slate-300">{description}</p>
      <div className="mt-5 flex flex-wrap gap-2">
        {bullets.map((bullet) => (
          <span
            key={bullet}
            className="rounded-full border border-slate-700 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.18em] text-slate-300"
          >
            {bullet}
          </span>
        ))}
      </div>
      <Link
        href={href}
        className={`mt-6 inline-flex rounded-2xl px-4 py-3 text-sm font-semibold uppercase tracking-[0.2em] transition ${
          disabled
            ? "cursor-not-allowed border border-slate-700 text-slate-500 pointer-events-none"
            : "bg-slate-100 text-slate-950 hover:bg-white"
        }`}
      >
        {cta}
      </Link>
    </div>
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
    <div className="rounded-[30px] border border-slate-800 bg-slate-900/70 p-6">
      <div className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-500">{title}</div>
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

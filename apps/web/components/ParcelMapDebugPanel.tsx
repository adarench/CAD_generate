type ParcelMapDebugPanelProps = {
  county: string;
  zoom: number | null;
  bbox: string;
  requestSummary: string;
  rawFeatureCount: number;
  renderedFeatureCount: number;
  zoomGateActive: boolean;
  fetchStatus: string;
  fetchError: string | null;
  mapStatus: string;
  mapError: string | null;
};

export function ParcelMapDebugPanel({
  county,
  zoom,
  bbox,
  requestSummary,
  rawFeatureCount,
  renderedFeatureCount,
  zoomGateActive,
  fetchStatus,
  fetchError,
  mapStatus,
  mapError,
}: ParcelMapDebugPanelProps) {
  return (
    <div className="absolute right-5 top-16 z-[500] w-[360px] rounded-[24px] border border-slate-800 bg-slate-950/94 p-4 shadow-2xl shadow-slate-950/70 backdrop-blur">
      <div className="text-[11px] uppercase tracking-[0.28em] text-emerald-300">Map Debug</div>
      <div className="mt-3 grid grid-cols-[1fr_1fr] gap-3 text-sm text-slate-300">
        <Metric label="County" value={county} />
        <Metric label="Zoom" value={zoom ? zoom.toFixed(2) : "—"} />
        <Metric label="Zoom gate" value={zoomGateActive ? "active" : "waiting"} />
        <Metric label="Fetch status" value={fetchStatus} />
        <Metric label="Map status" value={mapStatus} />
        <Metric label="Rendered" value={String(renderedFeatureCount)} />
      </div>
      <div className="mt-3 space-y-3 text-xs text-slate-400">
        <Block label="BBox" value={bbox} />
        <Block label="Request" value={requestSummary} />
        <Block label="Raw features" value={String(rawFeatureCount)} />
        <Block label="Rendered features" value={String(renderedFeatureCount)} />
        <Block label="Map error" value={mapError ?? "none"} tone={mapError ? "error" : "default"} />
        <Block label="Last error" value={fetchError ?? "none"} tone={fetchError ? "error" : "default"} />
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/80 px-3 py-2">
      <div className="text-[10px] uppercase tracking-[0.24em] text-slate-500">{label}</div>
      <div className="mt-1 text-sm text-slate-100">{value}</div>
    </div>
  );
}

function Block({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "error";
}) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/70 px-3 py-3">
      <div className="text-[10px] uppercase tracking-[0.24em] text-slate-500">{label}</div>
      <div className={`mt-1 break-words ${tone === "error" ? "text-red-300" : "text-slate-200"}`}>
        {value}
      </div>
    </div>
  );
}

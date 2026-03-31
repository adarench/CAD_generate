"use client";

export function WorkspaceSection({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-4 rounded-[28px] border border-slate-800 bg-slate-900/70 p-5 first:mt-0">
      <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500">{eyebrow}</div>
      <h2 className="mt-2 text-xl font-semibold text-slate-100">{title}</h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}

export function InfoTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[20px] border border-slate-800 bg-slate-950/70 px-4 py-4">
      <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">{label}</div>
      <div className="mt-2 text-sm text-slate-200">{value}</div>
    </div>
  );
}

export function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[20px] border border-slate-800 bg-slate-900/80 px-4 py-4">
      <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">{label}</div>
      <div className="mt-2 text-lg font-semibold text-slate-100">{value}</div>
    </div>
  );
}

export function StatusRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-[18px] border border-slate-800 bg-slate-950/70 px-4 py-3">
      <span className="text-slate-500">{label}</span>
      <span className={mono ? "font-mono text-slate-100" : "text-slate-100"}>{value}</span>
    </div>
  );
}

export function Alert({ tone, children }: { tone: "error" | "success"; children: React.ReactNode }) {
  const classes =
    tone === "error"
      ? "border-red-500/30 bg-red-500/10 text-red-200"
      : "border-emerald-400/30 bg-emerald-400/10 text-emerald-100";
  return <div className={`mt-4 rounded-[20px] border px-4 py-3 text-sm ${classes}`}>{children}</div>;
}

export function NumericInput({
  label,
  value,
  onChange,
  suffix,
  step = 1,
  helper,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  suffix?: string;
  step?: number;
  helper?: string;
}) {
  return (
    <label className="rounded-[20px] border border-slate-800 bg-slate-950/70 px-4 py-4">
      <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">{label}</div>
      <div className="mt-3 flex items-center gap-3">
        <input
          type="number"
          min={0}
          step={step}
          value={value}
          onChange={(event) => onChange(Number(event.target.value))}
          className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
        />
        {suffix ? <span className="text-xs uppercase tracking-[0.2em] text-slate-500">{suffix}</span> : null}
      </div>
      {helper ? <div className="mt-2 text-xs leading-5 text-slate-500">{helper}</div> : null}
    </label>
  );
}

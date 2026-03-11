import { StudioWorkspace } from "@/components/studio/StudioWorkspace";
import type { ParcelRecord, RunDetail } from "@/lib/parcels";

const BACKEND_URL = process.env.PYTHON_API_URL ?? "http://127.0.0.1:8000";

interface StudioPageProps {
  params: { parcelId: string };
}

async function fetchInitialParcel(parcelId: string) {
  const response = await fetch(`${BACKEND_URL}/api/parcels/${parcelId}`, { cache: "no-store" });
  if (!response.ok) {
    return null;
  }
  return (await response.json()) as ParcelRecord;
}

async function fetchInitialLatestRun(parcelId: string) {
  const response = await fetch(`${BACKEND_URL}/api/parcels/${parcelId}/latest-run`, { cache: "no-store" });
  if (!response.ok) {
    return null;
  }
  return (await response.json()) as RunDetail;
}

export default async function StudioPage({ params }: StudioPageProps) {
  const [initialParcel, initialRun] = await Promise.all([
    fetchInitialParcel(params.parcelId),
    fetchInitialLatestRun(params.parcelId),
  ]);
  return <StudioWorkspace parcelId={params.parcelId} initialParcel={initialParcel} initialRun={initialRun} />;
}

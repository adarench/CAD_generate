import { StudioWorkspace } from "@/components/studio/StudioWorkspace";

interface StudioPageProps {
  params: { parcelId: string };
}

export default function StudioPage({ params }: StudioPageProps) {
  return <StudioWorkspace parcelId={params.parcelId} />;
}

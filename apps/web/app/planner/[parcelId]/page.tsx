import { redirect } from "next/navigation";

interface PlannerRedirectPageProps {
  params: { parcelId: string };
}

export default function PlannerRedirectPage({ params }: PlannerRedirectPageProps) {
  redirect(`/studio/${params.parcelId}`);
}

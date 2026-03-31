import { DecisionReport } from "@/components/report/DecisionReport";

interface ReportPageProps {
  params: { parcelId: string };
}

export default function ReportPage({ params }: ReportPageProps) {
  return <DecisionReport parcelId={params.parcelId} />;
}

import type { DecisionRecord } from "@/lib/opportunities";
import { decisionRecordFromPipelineRun } from "@/lib/opportunities";
import type { PipelineRun } from "@/lib/parcels";

export type ParcelMemory = {
  parcel_id: string;
  latest: DecisionRecord;
  previous: DecisionRecord | null;
  runCount: number;
  lastUpdatedAt: string;
  statusHistory: Array<PipelineRun["status"]>;
  runs: PipelineRun[];
  changes: {
    statusChanged: boolean;
    unitsDelta: number | null;
    roiDelta: number | null;
    profitDelta: number | null;
    summary: string | null;
  };
};

export function buildParcelMemory(runs: PipelineRun[]): ParcelMemory | null {
  const sortedRuns = [...runs]
    .filter((run) => Boolean(run.parcel_id))
    .sort((left, right) => Date.parse(right.timestamp) - Date.parse(left.timestamp));
  if (!sortedRuns.length) return null;

  const latestRun = sortedRuns[0];
  const previousRun = sortedRuns[1] ?? null;
  const latest = decisionRecordFromPipelineRun(latestRun);
  const previous = previousRun ? decisionRecordFromPipelineRun(previousRun) : null;

  const latestUnits = latest.units;
  const previousUnits = previous?.units ?? null;
  const latestRoi = latest.ROI_base;
  const previousRoi = previous?.ROI_base ?? null;
  const latestProfit = latest.projected_profit;
  const previousProfit = previous?.projected_profit ?? null;

  const unitsDelta =
    typeof latestUnits === "number" && typeof previousUnits === "number"
      ? latestUnits - previousUnits
      : null;
  const roiDelta =
    typeof latestRoi === "number" && typeof previousRoi === "number"
      ? latestRoi - previousRoi
      : null;
  const profitDelta =
    typeof latestProfit === "number" && typeof previousProfit === "number"
      ? latestProfit - previousProfit
      : null;

  return {
    parcel_id: latestRun.parcel_id,
    latest,
    previous,
    runCount: sortedRuns.length,
    lastUpdatedAt: latestRun.timestamp,
    statusHistory: sortedRuns.map((run) => run.status),
    runs: sortedRuns,
    changes: {
      statusChanged: previous ? latest.status !== previous.status : false,
      unitsDelta,
      roiDelta,
      profitDelta,
      summary: buildChangeSummary(latest, previous, unitsDelta, roiDelta, profitDelta),
    },
  };
}

function buildChangeSummary(
  latest: DecisionRecord,
  previous: DecisionRecord | null,
  unitsDelta: number | null,
  roiDelta: number | null,
  profitDelta: number | null
) {
  if (!previous) return "First recorded decision for this parcel.";

  const changes: string[] = [];
  if (latest.decision_label !== previous.decision_label) {
    changes.push(`recommendation changed from ${previous.decision_label} to ${latest.decision_label}`);
  }
  if (typeof roiDelta === "number" && Math.abs(roiDelta) >= 0.005) {
    changes.push(`ROI ${roiDelta > 0 ? "up" : "down"} ${Math.abs(roiDelta * 100).toFixed(1)} pts`);
  }
  if (typeof profitDelta === "number" && Math.abs(profitDelta) >= 1000) {
    changes.push(`profit ${profitDelta > 0 ? "up" : "down"} ${formatCompactCurrency(Math.abs(profitDelta))}`);
  }
  if (typeof unitsDelta === "number" && unitsDelta !== 0) {
    changes.push(`units ${unitsDelta > 0 ? "up" : "down"} ${Math.abs(unitsDelta)}`);
  }

  return changes.length ? changes.join(" • ") : "No material change from the previous saved run.";
}

function formatCompactCurrency(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

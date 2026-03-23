import type { ParcelRecord } from "@/lib/parcels";

export type OpportunityFilterState = {
  minAcreage: number;
  likelyUndevelopedOnly: boolean;
  residentialCompatibleOnly: boolean;
  hideTinyDevelopedLots: boolean;
};

export type OpportunityAssessment = {
  parcelId: string;
  score: number;
  tier: "high" | "medium" | "low" | "none";
  likelyCandidate: boolean;
  likelyUndeveloped: boolean;
  likelyDeveloped: boolean;
  residentialCompatible: boolean;
  residentialConfidence: "explicit" | "heuristic" | "unknown";
  reasons: string[];
  warnings: string[];
  failedFilters: string[];
};

const NON_RESIDENTIAL_PATTERNS = [
  "industrial",
  "commercial",
  "office",
  "retail",
  "utility",
  "school",
  "church",
  "airport",
  "hospital",
  "warehouse",
  "mining",
  "quarry",
];

const RESIDENTIAL_PATTERNS = ["residential", "single family", "multi family", "r-", "rm", "rr", "res"];

export const DEFAULT_OPPORTUNITY_FILTERS: OpportunityFilterState = {
  minAcreage: 2,
  likelyUndevelopedOnly: true,
  residentialCompatibleOnly: true,
  hideTinyDevelopedLots: true,
};

export function assessOpportunity(parcel: ParcelRecord, filters: OpportunityFilterState): OpportunityAssessment {
  const acreage = parcel.areaAcres ?? 0;
  const address = (parcel.address ?? "").trim();
  const landUse = normalize(parcel.landUse);
  const zoning = normalize(parcel.zoningCode);
  const residentialSignal = [zoning, landUse].filter(Boolean).join(" ");
  const hasAddress = address.length > 0 && address.toLowerCase() !== "unavailable";
  const likelyUndeveloped = !hasAddress || acreage >= 5;
  const likelyDeveloped = hasAddress && acreage < 5;

  const hasExplicitResidentialSignal = RESIDENTIAL_PATTERNS.some((pattern) => residentialSignal.includes(pattern));
  const hasExplicitNonResidentialSignal = NON_RESIDENTIAL_PATTERNS.some((pattern) =>
    residentialSignal.includes(pattern)
  );

  let residentialCompatible = true;
  let residentialConfidence: OpportunityAssessment["residentialConfidence"] = "unknown";
  if (hasExplicitNonResidentialSignal) {
    residentialCompatible = false;
    residentialConfidence = "explicit";
  } else if (hasExplicitResidentialSignal) {
    residentialCompatible = true;
    residentialConfidence = "explicit";
  } else if (zoning || landUse) {
    residentialCompatible = true;
    residentialConfidence = "heuristic";
  }

  const reasons: string[] = [];
  const warnings: string[] = [];
  const failedFilters: string[] = [];

  reasons.push(`${formatAcres(acreage)} parcel footprint`);
  if (!hasAddress) {
    reasons.push("No situs address in normalized parcel record");
  } else if (acreage >= 5) {
    reasons.push("Large-acreage parcel retained despite address presence");
  } else {
    warnings.push("Address present; parcel may already be developed");
  }

  if (residentialConfidence === "explicit" && residentialCompatible) {
    reasons.push("Residential-compatible signal found in source attributes");
  } else if (!residentialCompatible) {
    warnings.push("Explicit non-residential signal found in zoning or land-use fields");
  } else {
    warnings.push("Residential compatibility is heuristic; no zoning join is available yet");
  }

  let score = 0;
  if (acreage >= filters.minAcreage) score += 2;
  if (acreage >= 5) score += 1;
  if (likelyUndeveloped) score += 2;
  if (!likelyDeveloped && acreage >= 10) score += 1;
  if (residentialCompatible) score += residentialConfidence === "explicit" ? 2 : 1;

  if (acreage < filters.minAcreage) {
    failedFilters.push(`Below minimum acreage (${filters.minAcreage} ac)`);
  }
  if (filters.likelyUndevelopedOnly && !likelyUndeveloped) {
    failedFilters.push("Likely developed by address heuristic");
  }
  if (filters.residentialCompatibleOnly && !residentialCompatible) {
    failedFilters.push("Explicit non-residential compatibility signal");
  }
  if (filters.hideTinyDevelopedLots && likelyDeveloped && acreage < 1) {
    failedFilters.push("Tiny addressed lot hidden");
  }

  const likelyCandidate = failedFilters.length === 0 && score >= 3;
  const tier: OpportunityAssessment["tier"] =
    !likelyCandidate ? "none" : score >= 6 ? "high" : score >= 4 ? "medium" : "low";

  return {
    parcelId: parcel.id,
    score,
    tier,
    likelyCandidate,
    likelyUndeveloped,
    likelyDeveloped,
    residentialCompatible,
    residentialConfidence,
    reasons,
    warnings,
    failedFilters,
  };
}

export function summarizeOpportunity(assessment: OpportunityAssessment): string {
  if (!assessment.likelyCandidate) {
    return assessment.failedFilters[0] ?? "This parcel does not pass the current opportunity heuristic.";
  }
  return `${capitalize(assessment.tier)}-confidence opportunity based on acreage, address absence, and available compatibility signals.`;
}

export function opportunityBadgeLabel(assessment: OpportunityAssessment): string {
  if (!assessment.likelyCandidate) return "Filtered out";
  return `${capitalize(assessment.tier)} opportunity`;
}

function normalize(value: string | null | undefined) {
  return (value ?? "").trim().toLowerCase();
}

function formatAcres(value: number) {
  return `${value.toFixed(2)} ac`;
}

function capitalize(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

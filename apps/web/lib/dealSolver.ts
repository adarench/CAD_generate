/**
 * Frontend-only deal threshold solver.
 *
 * Mirrors the ROI formula from bedrock/services/feasibility_service.py
 * so we can binary-search for the minimum single-variable change
 * that reaches a target ROI — without calling the backend.
 */

/* ── Constants (match feasibility_service.py) ── */

const UTILITY_COST_FACTOR = 0.55;
const GRADING_COST_FACTOR = 0.10;
const PERMITTING_COST_PER_UNIT = 3500;
const SITEWORK_COST_PER_ACRE = 18000;
const SQFT_PER_ACRE = 43560;

const MAX_ITERATIONS = 30;
const ROI_TOLERANCE = 0.001; // ±0.1 percentage points

/* ── Types ── */

export type SolverVariable = "home_price" | "construction_cost" | "land_price";

export type SolverInput = {
  units: number;
  roadLengthFt: number;
  utilityLengthFt: number;
  parcelAreaSqft: number;
  currentHomePrice: number;
  currentCostPerHome: number;
  currentLandPrice: number;
  roadCostPerFt: number;
};

export type SolverResult = {
  variable: SolverVariable;
  label: string;
  requiredValue: number;
  currentValue: number;
  changePercent: number;
  resultingRoi: number;
  resultingProfit: number;
  achievable: boolean;
};

export type ROIOutput = {
  roi: number | null;
  projectedProfit: number;
  projectedRevenue: number;
  projectedCost: number;
};

/* ── Core ROI computation ── */

export function computeROI(
  homePrice: number,
  costPerHome: number,
  landPrice: number,
  roadCostPerFt: number,
  layout: { units: number; roadLengthFt: number; utilityLengthFt: number; parcelAreaSqft: number },
): ROIOutput {
  const { units, roadLengthFt, utilityLengthFt, parcelAreaSqft } = layout;

  const projectedRevenue = units * homePrice;

  const roadsCost = roadLengthFt * roadCostPerFt;
  const utilitiesCost = utilityLengthFt * roadCostPerFt * UTILITY_COST_FACTOR;
  const gradingCost = (roadsCost + utilitiesCost) * GRADING_COST_FACTOR;
  const permittingCost = units * PERMITTING_COST_PER_UNIT;
  const siteworkCost = (parcelAreaSqft / SQFT_PER_ACRE) * SITEWORK_COST_PER_ACRE;

  const developmentTotal = roadsCost + utilitiesCost + gradingCost + permittingCost + siteworkCost;
  const constructionTotal = units * costPerHome;
  const projectedCost = constructionTotal + developmentTotal + landPrice;

  const projectedProfit = projectedRevenue - projectedCost;
  const roi = projectedCost === 0 ? null : projectedProfit / projectedCost;

  return { roi, projectedProfit, projectedRevenue, projectedCost };
}

/* ── Binary search solver ── */

function solveForVariable(
  input: SolverInput,
  variable: SolverVariable,
  targetRoi: number,
): SolverResult {
  const layout = {
    units: input.units,
    roadLengthFt: input.roadLengthFt,
    utilityLengthFt: input.utilityLengthFt,
    parcelAreaSqft: input.parcelAreaSqft,
  };

  const labels: Record<SolverVariable, string> = {
    home_price: "home price",
    construction_cost: "construction cost",
    land_price: "land basis",
  };

  const currentValues: Record<SolverVariable, number> = {
    home_price: input.currentHomePrice,
    construction_cost: input.currentCostPerHome,
    land_price: input.currentLandPrice,
  };

  const currentValue = currentValues[variable];

  // Define search bounds
  let lower: number;
  let upper: number;

  if (variable === "home_price") {
    lower = currentValue;
    upper = currentValue * 2;
  } else if (variable === "construction_cost") {
    lower = currentValue * 0.5;
    upper = currentValue;
  } else {
    // land_price: decrease from current to 0
    lower = 0;
    upper = currentValue;
  }

  // Build the ROI evaluator for this variable
  function evalRoi(testValue: number): ROIOutput {
    const hp = variable === "home_price" ? testValue : input.currentHomePrice;
    const cc = variable === "construction_cost" ? testValue : input.currentCostPerHome;
    const lp = variable === "land_price" ? testValue : input.currentLandPrice;
    return computeROI(hp, cc, lp, input.roadCostPerFt, layout);
  }

  // Check if target is achievable at the extreme bound
  const extremeValue = variable === "home_price" ? upper : lower;
  const extremeResult = evalRoi(extremeValue);
  if (extremeResult.roi === null || extremeResult.roi < targetRoi) {
    return {
      variable,
      label: labels[variable],
      requiredValue: extremeValue,
      currentValue,
      changePercent: currentValue === 0 ? 0 : ((extremeValue - currentValue) / currentValue) * 100,
      resultingRoi: extremeResult.roi ?? 0,
      resultingProfit: extremeResult.projectedProfit,
      achievable: false,
    };
  }

  // Binary search: find the value closest to current that still meets target
  // For home_price: search upward (lower = current, upper = 2×current)
  // For cost/land: search downward (lower = floor, upper = current)
  let lo = lower;
  let hi = upper;

  for (let i = 0; i < MAX_ITERATIONS; i++) {
    const mid = (lo + hi) / 2;
    const midResult = evalRoi(mid);
    const midRoi = midResult.roi ?? -Infinity;

    if (Math.abs(midRoi - targetRoi) < ROI_TOLERANCE) {
      // Close enough
      lo = mid;
      hi = mid;
      break;
    }

    if (variable === "home_price") {
      // Increasing price increases ROI — if mid meets target, try lower (closer to current)
      if (midRoi >= targetRoi) {
        hi = mid;
      } else {
        lo = mid;
      }
    } else {
      // Decreasing cost/land increases ROI — if mid meets target, try higher (closer to current)
      if (midRoi >= targetRoi) {
        lo = mid;
      } else {
        hi = mid;
      }
    }
  }

  // Use the conservative bound (the one guaranteed to meet the target)
  const finalValue = variable === "home_price" ? hi : lo;
  const finalResult = evalRoi(finalValue);

  return {
    variable,
    label: labels[variable],
    requiredValue: Math.round(finalValue),
    currentValue,
    changePercent: currentValue === 0 ? 0 : ((finalValue - currentValue) / currentValue) * 100,
    resultingRoi: finalResult.roi ?? 0,
    resultingProfit: finalResult.projectedProfit,
    achievable: true,
  };
}

/* ── Public API ── */

export function solveDeal(input: SolverInput, targetRoi: number = 0.10): SolverResult[] {
  const variables: SolverVariable[] = ["home_price", "construction_cost", "land_price"];

  // Skip land_price if current is 0 (can't decrease from 0)
  const activeVariables = variables.filter((v) => {
    if (v === "land_price" && input.currentLandPrice <= 0) return false;
    return true;
  });

  const results = activeVariables.map((v) => solveForVariable(input, v, targetRoi));

  // Sort: achievable first, then by smallest |changePercent|
  return results.sort((a, b) => {
    if (a.achievable !== b.achievable) return a.achievable ? -1 : 1;
    return Math.abs(a.changePercent) - Math.abs(b.changePercent);
  });
}

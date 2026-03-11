import type { ConceptInstruction } from "@/lib/parcels";

export const CONCEPT_PRESET_CHIPS = [
  {
    label: "Collector + loops",
    instruction: "Create a subdivision concept with a central collector road and two loop streets.",
  },
  {
    label: "Cul-de-sacs",
    instruction: "Use cul-de-sacs instead of loops and keep the road network simple.",
  },
  {
    label: "Larger south edge lots",
    instruction: "Create larger lots along the southern edge and reduce the overall density.",
  },
  {
    label: "Spine + locals",
    instruction: "Add a spine road with perpendicular local streets and moderate density.",
  },
  {
    label: "Simplify layout",
    instruction: "Reduce density and simplify the road layout. Avoid parallel collectors.",
  },
] as const;

export function summarizeAppliedInstruction(instruction?: ConceptInstruction | null) {
  if (!instruction) {
    return "Manual parcel layout using the current assumptions.";
  }

  const phrases: string[] = [];
  if (instruction.topologyPreferences?.length) {
    phrases.push(`topologies: ${instruction.topologyPreferences.join(", ")}`);
  }
  if (instruction.excludedTopologies?.length) {
    phrases.push(`avoiding ${instruction.excludedTopologies.join(", ")}`);
  }
  if (instruction.densityIntent) {
    phrases.push(`${instruction.densityIntent} density`);
  }
  if (instruction.roadIntent) {
    phrases.push(instruction.roadIntent);
  }
  if (instruction.lotIntent) {
    phrases.push(instruction.lotIntent);
  }
  if (instruction.edgeConditions?.length) {
    phrases.push(`edge focus: ${instruction.edgeConditions.join(", ")}`);
  }
  if (instruction.notes) {
    phrases.push(instruction.notes);
  }

  return phrases.length ? phrases.join(" • ") : "Manual parcel layout using the current assumptions.";
}

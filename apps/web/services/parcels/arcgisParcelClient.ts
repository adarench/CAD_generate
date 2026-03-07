export const SUPPORTED_UTAH_COUNTIES = [
  "Beaver",
  "Box Elder",
  "Cache",
  "Carbon",
  "Daggett",
  "Davis",
  "Duchesne",
  "Emery",
  "Garfield",
  "Grand",
  "Iron",
  "Juab",
  "Kane",
  "Millard",
  "Morgan",
  "Piute",
  "Rich",
  "Salt Lake",
  "San Juan",
  "Sanpete",
  "Sevier",
  "Summit",
  "Tooele",
  "Uintah",
  "Utah",
  "Wasatch",
  "Washington",
  "Wayne",
  "Weber",
] as const;

const COUNTY_OVERRIDES: Record<string, string> = {
  "Salt Lake": "SaltLake",
  "San Juan": "SanJuan",
  Juab: "Juab",
};

export function countyServiceUrl(county: string) {
  const slug = COUNTY_OVERRIDES[county] ?? county.replace(/[^A-Za-z0-9]/g, "");
  return `https://services1.arcgis.com/99lidPhWCzftIe9K/ArcGIS/rest/services/Parcels_${slug}/FeatureServer/0`;
}

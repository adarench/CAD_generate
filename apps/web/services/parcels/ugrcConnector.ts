import { countyServiceUrl } from "./arcgisParcelClient";

export const UGRC_CONNECTOR = {
  provider: "UGRC ArcGIS REST",
  datasetForCounty(county: string) {
    return `Parcels_${county}`;
  },
  serviceUrl(county: string) {
    return countyServiceUrl(county);
  },
};

export type MapViewState = {
  lng: number;
  lat: number;
  zoom: number;
};

export type BasemapMode = "drawing" | "gis" | "aerial";

export const DEFAULT_MAP_COUNTY = "Salt Lake";
export const DEFAULT_STUDIO_DEMO_PARCEL_ID = "ut-SaltLake-03201000010000";
export const DEFAULT_STUDIO_DEMO_APN = "03201000010000";

export const COUNTY_DEFAULT_VIEWS: Record<string, MapViewState> = {
  "Salt Lake": { lng: -111.83684683892612, lat: 40.61985292120375, zoom: 16.35 },
  Utah: { lng: -111.6588, lat: 40.2969, zoom: 14.8 },
  Davis: { lng: -111.8924, lat: 40.8872, zoom: 14.4 },
  Washington: { lng: -113.5892, lat: 37.1115, zoom: 14.5 },
};

export const DEFAULT_MAP_VIEW = COUNTY_DEFAULT_VIEWS[DEFAULT_MAP_COUNTY];

export const GIS_BASEMAP_TILE_URL = "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png";

export const GIS_BASEMAP_SUBDOMAINS = ["a", "b", "c", "d"];

export const GIS_REFERENCE_TILE_URL = "";

export const AERIAL_BASEMAP_TILE_URL =
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";

export const GIS_BASEMAP_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>';

export const AERIAL_BASEMAP_ATTRIBUTION =
  '&copy; <a href="https://www.esri.com/">Esri</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

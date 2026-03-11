"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchParcelsInBounds } from "@/lib/api";

type ViewportBounds = {
  minLng: number;
  minLat: number;
  maxLng: number;
  maxLat: number;
  zoom: number;
} | null;

export const PARCEL_VIEWPORT_MIN_ZOOM = 9;
export const DEFAULT_PARCEL_VIEWPORT_LIMIT = 2000;

export function parcelViewportLimitForZoom(zoom: number | null | undefined) {
  if (!zoom) return DEFAULT_PARCEL_VIEWPORT_LIMIT;
  if (zoom < 11) return 500;
  if (zoom <= 13) return 2000;
  return 5000;
}

export function useParcelViewportQuery(county: string, viewport: ViewportBounds, limit?: number) {
  const resolvedLimit = limit ?? parcelViewportLimitForZoom(viewport?.zoom);
  return useQuery({
    queryKey: [
      "visible-parcels",
      county,
      viewport?.minLng,
      viewport?.minLat,
      viewport?.maxLng,
      viewport?.maxLat,
      viewport?.zoom,
      resolvedLimit,
    ],
    queryFn: () =>
      fetchParcelsInBounds(
        county,
        {
          minLng: viewport!.minLng,
          minLat: viewport!.minLat,
          maxLng: viewport!.maxLng,
          maxLat: viewport!.maxLat,
        },
        resolvedLimit,
        viewport!.zoom
      ),
    enabled: Boolean(viewport && viewport.zoom >= PARCEL_VIEWPORT_MIN_ZOOM),
    keepPreviousData: true,
    staleTime: 15000,
    retry: 1,
    refetchOnWindowFocus: false,
  });
}

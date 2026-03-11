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

export function useParcelViewportQuery(county: string, viewport: ViewportBounds, limit = 150) {
  return useQuery({
    queryKey: [
      "visible-parcels",
      county,
      viewport?.minLng,
      viewport?.minLat,
      viewport?.maxLng,
      viewport?.maxLat,
      viewport?.zoom,
      limit,
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
        limit
      ),
    enabled: Boolean(viewport && viewport.zoom >= PARCEL_VIEWPORT_MIN_ZOOM),
    keepPreviousData: true,
    staleTime: 15000,
    retry: 1,
    refetchOnWindowFocus: false,
  });
}

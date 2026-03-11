"use client";

import dynamic from "next/dynamic";

export const ClientMapView = dynamic(
  () => import("@/components/MapView").then((module) => module.MapView),
  { ssr: false }
);

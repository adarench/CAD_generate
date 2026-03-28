"use client";

import { useEffect, useMemo, useState } from "react";

const SHORTLIST_STORAGE_KEY = "land-intelligence-shortlist";

export function shortlistStorageKey() {
  return SHORTLIST_STORAGE_KEY;
}

export function readShortlistIds(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(SHORTLIST_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((entry): entry is string => typeof entry === "string");
  } catch {
    return [];
  }
}

export function writeShortlistIds(ids: string[]) {
  if (typeof window === "undefined") return;
  const next = Array.from(new Set(ids));
  window.localStorage.setItem(SHORTLIST_STORAGE_KEY, JSON.stringify(next));
  window.dispatchEvent(new CustomEvent("shortlist:updated", { detail: next }));
}

export function useShortlist() {
  const [shortlistIds, setShortlistIds] = useState<string[]>([]);

  useEffect(() => {
    setShortlistIds(readShortlistIds());

    function syncFromStorage() {
      setShortlistIds(readShortlistIds());
    }

    function syncFromEvent(event: Event) {
      const customEvent = event as CustomEvent<string[]>;
      if (Array.isArray(customEvent.detail)) {
        setShortlistIds(customEvent.detail);
        return;
      }
      syncFromStorage();
    }

    window.addEventListener("storage", syncFromStorage);
    window.addEventListener("shortlist:updated", syncFromEvent as EventListener);
    return () => {
      window.removeEventListener("storage", syncFromStorage);
      window.removeEventListener("shortlist:updated", syncFromEvent as EventListener);
    };
  }, []);

  const api = useMemo(
    () => ({
      shortlistIds,
      isShortlisted: (parcelId: string) => shortlistIds.includes(parcelId),
      addToShortlist: (parcelId: string) => writeShortlistIds([...shortlistIds, parcelId]),
      removeFromShortlist: (parcelId: string) =>
        writeShortlistIds(shortlistIds.filter((entry) => entry !== parcelId)),
      toggleShortlist: (parcelId: string) =>
        writeShortlistIds(
          shortlistIds.includes(parcelId)
            ? shortlistIds.filter((entry) => entry !== parcelId)
            : [...shortlistIds, parcelId]
        ),
      clearShortlist: () => writeShortlistIds([]),
    }),
    [shortlistIds]
  );

  return api;
}

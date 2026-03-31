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

function syncAddToServer(parcelId: string) {
  fetch("/api/shortlist", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ parcel_id: parcelId }),
  }).catch(() => {});
}

function syncRemoveFromServer(parcelId: string) {
  fetch(`/api/shortlist/${parcelId}`, { method: "DELETE" }).catch(() => {});
}

function syncClearServer() {
  fetch("/api/shortlist", { method: "DELETE" }).catch(() => {});
}

async function loadFromServer(): Promise<string[]> {
  try {
    const response = await fetch("/api/shortlist");
    if (!response.ok) return [];
    const items: Array<{ parcel_id: string }> = await response.json();
    return items.map((i) => i.parcel_id);
  } catch {
    return [];
  }
}

export function useShortlist() {
  const [shortlistIds, setShortlistIds] = useState<string[]>([]);
  const [serverLoaded, setServerLoaded] = useState(false);

  useEffect(() => {
    const localIds = readShortlistIds();
    setShortlistIds(localIds);

    loadFromServer().then((serverIds) => {
      const merged = Array.from(new Set([...localIds, ...serverIds]));
      if (merged.length !== localIds.length || merged.some((id) => !localIds.includes(id))) {
        writeShortlistIds(merged);
        setShortlistIds(merged);
        for (const id of localIds) {
          if (!serverIds.includes(id)) syncAddToServer(id);
        }
      }
      setServerLoaded(true);
    });

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
      addToShortlist: (parcelId: string) => {
        writeShortlistIds([...shortlistIds, parcelId]);
        syncAddToServer(parcelId);
      },
      removeFromShortlist: (parcelId: string) => {
        writeShortlistIds(shortlistIds.filter((entry) => entry !== parcelId));
        syncRemoveFromServer(parcelId);
      },
      toggleShortlist: (parcelId: string) => {
        if (shortlistIds.includes(parcelId)) {
          writeShortlistIds(shortlistIds.filter((entry) => entry !== parcelId));
          syncRemoveFromServer(parcelId);
        } else {
          writeShortlistIds([...shortlistIds, parcelId]);
          syncAddToServer(parcelId);
        }
      },
      clearShortlist: () => {
        writeShortlistIds([]);
        syncClearServer();
      },
    }),
    [shortlistIds]
  );

  return api;
}

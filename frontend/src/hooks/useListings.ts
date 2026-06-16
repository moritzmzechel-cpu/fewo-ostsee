import { useState, useEffect, useCallback } from "react";

export interface Listing {
  id: number;
  name: string;
  ort: string;
  region: string;
  bild_url: string | null;
  personen_max: number | null;
  latitude: number | null;
  longitude: number | null;
  letzter_preis_nacht: number | null;
}

export interface Filters {
  ort: string;
  min_personen: string;
  max_personen: string;
  min_preis: string;
  max_preis: string;
  haustiere: string;
}

export function useListings(filters: Filters) {
  const [listings, setListings] = useState<Listing[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch_ = useCallback(async () => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams();
    if (filters.ort) params.set("ort", filters.ort);
    if (filters.min_personen) params.set("min_personen", filters.min_personen);
    if (filters.max_personen) params.set("max_personen", filters.max_personen);
    if (filters.min_preis) params.set("min_preis", filters.min_preis);
    if (filters.max_preis) params.set("max_preis", filters.max_preis);
    if (filters.haustiere) params.set("haustiere", filters.haustiere);
    try {
      const res = await fetch(`/listings/?${params}`);
      if (!res.ok) throw new Error(`API Fehler ${res.status}`);
      setListings(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unbekannter Fehler");
    } finally {
      setLoading(false);
    }
  }, [filters.ort, filters.min_personen, filters.max_personen, filters.min_preis, filters.max_preis, filters.haustiere]);

  useEffect(() => { fetch_(); }, [fetch_]);

  return { listings, loading, error };
}

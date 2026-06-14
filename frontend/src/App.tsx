import { useState } from "react";
import { FilterPanel } from "./components/FilterPanel";
import { ListingList } from "./components/ListingList";
import { Map } from "./components/Map";
import { useListings, Filters } from "./hooks/useListings";

const DEFAULT_FILTERS: Filters = {
  ort: "",
  min_personen: "",
  max_personen: "",
  min_preis: "",
  max_preis: "",
  haustiere: "",
};

export default function App() {
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [selected, setSelected] = useState<number | null>(null);
  const { listings, loading, error } = useListings(filters);

  return (
    <div className="app">
      <header>
        <h1>FeWo Ostsee SH</h1>
        <span>Ferienwohnungen · Schlei-Region</span>
      </header>
      <div className="main">
        <div className="sidebar">
          <FilterPanel filters={filters} onChange={setFilters} />
          <div className="stats-bar">
            {loading ? "Lade…" : `${listings.length} Ferienwohnungen`}
          </div>
          <ListingList
            listings={listings}
            loading={loading}
            error={error}
            selected={selected}
            onSelect={setSelected}
          />
        </div>
        <Map listings={listings} selected={selected} onSelect={setSelected} />
      </div>
    </div>
  );
}

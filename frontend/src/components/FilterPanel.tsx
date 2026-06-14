import { Filters } from "../hooks/useListings";

interface Props {
  filters: Filters;
  onChange: (f: Filters) => void;
}

export function FilterPanel({ filters, onChange }: Props) {
  const set = (key: keyof Filters) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    onChange({ ...filters, [key]: e.target.value });

  return (
    <div className="filters">
      <h2>Filter</h2>
      <div className="filter-row">
        <input
          placeholder="Ort (z.B. Schleswig)"
          value={filters.ort}
          onChange={set("ort")}
        />
      </div>
      <div className="filter-row">
        <label>Personen</label>
        <input type="number" placeholder="min" value={filters.min_personen} onChange={set("min_personen")} />
        <input type="number" placeholder="max" value={filters.max_personen} onChange={set("max_personen")} />
      </div>
      <div className="filter-row">
        <label>Preis/Nacht €</label>
        <input type="number" placeholder="min" value={filters.min_preis} onChange={set("min_preis")} />
        <input type="number" placeholder="max" value={filters.max_preis} onChange={set("max_preis")} />
      </div>
      <div className="filter-row">
        <select value={filters.haustiere} onChange={set("haustiere")}>
          <option value="">Haustiere — egal</option>
          <option value="true">Haustiere erlaubt</option>
          <option value="false">Keine Haustiere</option>
        </select>
      </div>
    </div>
  );
}

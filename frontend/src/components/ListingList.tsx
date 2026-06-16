import { Listing } from "../hooks/useListings";

interface Props {
  listings: Listing[];
  loading: boolean;
  error: string | null;
  selected: number | null;
  onSelect: (id: number) => void;
}

export function ListingList({ listings, loading, error, selected, onSelect }: Props) {
  if (loading) return <div className="empty">Lade Daten…</div>;
  if (error) return <div className="empty" style={{ color: "#e53e3e" }}>Fehler: {error}<br /><small>Backend läuft?</small></div>;
  if (!listings.length) return <div className="empty">Keine Ergebnisse</div>;

  return (
    <div className="listings">
      {listings.map((l) => (
        <div
          key={l.id}
          className={`listing-card${selected === l.id ? " active" : ""}`}
          onClick={() => onSelect(l.id)}
        >
          <div className="listing-card-body">
            {l.bild_url && (
              <img className="listing-thumb" src={l.bild_url} alt="" loading="lazy" />
            )}
            <div>
              <h3>{l.name}</h3>
              <div className="listing-meta">
                <span>{l.ort}</span>
                {l.personen_max && <span>· {l.personen_max} Pers.</span>}
                {l.letzter_preis_nacht && (
                  <span className="listing-price">· ab {l.letzter_preis_nacht} €/Nacht</span>
                )}
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

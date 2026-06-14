import { MapContainer, TileLayer, Marker, Popup, useMap } from "react-leaflet";
import { Listing } from "../hooks/useListings";
import { useEffect } from "react";
import L from "leaflet";

// Leaflet-Icon-Fix für Vite
delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

const selectedIcon = new L.Icon({
  iconUrl: "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-red.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
});

function FlyTo({ listing }: { listing: Listing | undefined }) {
  const map = useMap();
  useEffect(() => {
    if (listing?.latitude && listing?.longitude) {
      map.flyTo([listing.latitude, listing.longitude], 13, { duration: 0.8 });
    }
  }, [listing, map]);
  return null;
}

interface Props {
  listings: Listing[];
  selected: number | null;
  onSelect: (id: number) => void;
}

// Schlei-Region als Mittelpunkt
const SCHLEI_CENTER: [number, number] = [54.62, 9.85];

export function Map({ listings, selected, onSelect }: Props) {
  const withGeo = listings.filter((l) => l.latitude && l.longitude);
  const selectedListing = listings.find((l) => l.id === selected);

  return (
    <div className="map-container" style={{ height: "100%" }}>
      <MapContainer center={SCHLEI_CENTER} zoom={10} style={{ height: "100%", width: "100%" }}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FlyTo listing={selectedListing} />
        {withGeo.map((l) => (
          <Marker
            key={l.id}
            position={[l.latitude!, l.longitude!]}
            icon={selected === l.id ? selectedIcon : new L.Icon.Default()}
            eventHandlers={{ click: () => onSelect(l.id) }}
          >
            <Popup>
              <strong>{l.name}</strong><br />
              {l.ort} · {l.personen_max ?? "?"} Pers.
              {l.letzter_preis_nacht && <><br />{l.letzter_preis_nacht} €/Nacht</>}
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}

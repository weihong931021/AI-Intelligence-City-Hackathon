import "leaflet/dist/leaflet.css";

import L from "leaflet";
import markerIcon2xUrl from "leaflet/dist/images/marker-icon-2x.png?url";
import markerIconUrl from "leaflet/dist/images/marker-icon.png?url";
import markerShadowUrl from "leaflet/dist/images/marker-shadow.png?url";
import { type FC, useEffect } from "react";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";

import type { LatLng } from "@/agent/tools";
import { cn } from "@/lib/utils";

// Vite 打包後 Leaflet 找不到預設圖示；Icon.Default 會再前綴 imagePath 造成路徑重複，改用明確網址的 L.icon。
const markerIcon = L.icon({
  iconRetinaUrl: markerIcon2xUrl,
  iconUrl: markerIconUrl,
  shadowUrl: markerShadowUrl,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  tooltipAnchor: [16, -28],
  shadowSize: [41, 41],
});

/** 容器尺寸改變時（分割面板拖動、視窗縮放）重新量測地圖。 */
const InvalidateOnResize: FC = () => {
  const map = useMap();
  useEffect(() => {
    const el = map.getContainer();
    const ro = new ResizeObserver(() => map.invalidateSize());
    ro.observe(el);
    return () => ro.disconnect();
  }, [map]);
  return null;
};

type Props = { center: LatLng; subject?: LatLng; comparables: LatLng[]; className?: string };

/** 先隨便串一個 OSM 底圖，之後換成法定地圖出圖結果。 */
export const CaseMap: FC<Props> = ({ center, subject, comparables, className }) => (
  <div className={cn("h-64 w-full overflow-hidden rounded-[14px] border border-border", className)}>
    <MapContainer center={[center.lat, center.lng]} zoom={15} scrollWheelZoom={false} className="h-full w-full">
      <InvalidateOnResize />
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors (ODbL)'
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {subject && (
        <Marker position={[subject.lat, subject.lng]} icon={markerIcon}>
          <Popup>{subject.label}</Popup>
        </Marker>
      )}
      {comparables.map((c, i) => (
        <Marker key={i} position={[c.lat, c.lng]} icon={markerIcon}>
          <Popup>{c.label}</Popup>
        </Marker>
      ))}
    </MapContainer>
  </div>
);

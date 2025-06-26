import { useRef, useState } from "react";
import Map, {
  CircleLayer,
  SymbolLayer,
  Layer,
  Source,
  MapLayerMouseEvent,
  MapRef,
  Popup,
} from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import "@sfgov/design-system/dist/css/sfds.css";

import geojson from "../../map_data/public_pools.json";
import data from "../../map_data/latest_family_swim_data.json";
import { PoolDictionary, Weekday, PoolEnum } from "./poolDataTypes";
import { generateGeoJSONLayers, getCurrentWeekday } from "./utils";
import { ControlPanel } from "./ControlPanel";

const poolData = data as PoolDictionary;
const constructedLayers = generateGeoJSONLayers(geojson, poolData);

const circleLayerStyle: CircleLayer = {
  id: "locations",
  type: "circle",
  paint: {
    "circle-radius": 10,
    "circle-color": "#5A7A92",
  },
};

const textLayerStyle: SymbolLayer = {
  id: "location-labels",
  type: "symbol",
  layout: {
    "text-field": ["get", "name"],
    "text-anchor": "left",
    "text-offset": [1, 0],
    "text-size": 12,
    "text-font": ["Open Sans Bold"],
    "text-allow-overlap": true,
  },
  paint: {
    "text-color": "#002B48",
  },
};

const timesLayerStyle: SymbolLayer = {
  id: "dayPoolTime-labels",
  type: "symbol",
  layout: {
    "text-field": ["get", "times"],
    "text-anchor": "top",
    "text-offset": [0, 1],
    "text-size": 12,
    "text-font": ["Open Sans Bold"],
    "text-allow-overlap": true,
  },
  paint: {
    "text-color": "#495ED4",
  },
};

export const SFMap = () => {
  const mapRef = useRef<MapRef>(null);
  const [popupInfo, setPopupInfo] = useState(null);
  //
  const [selectedDay, setSelectedDay] = useState<Weekday>(getCurrentWeekday());

  // useEffect(() => {
  //   console.log("🚀 ~ useEffect ~ mapRef.current?:", mapRef.current);
  //   async function addImage() {
  //     if (!mapRef.current) return;
  //     const image = await mapRef.current.loadImage("/swimming.png");
  //     mapRef.current?.addImage("swimming", image.data);
  //   }
  //   if (!mapRef.current) return;
  //   mapRef.current.addImage();
  // }, [mapRef.current]);

  const onClickMap = (event: MapLayerMouseEvent) => {
    const features = event.features;
    console.log("🚀 ~ onClickMap ~ features:", features);
    if (features && features.length > 0) {
      const feature = features[0];
      setPopupInfo({
        longitude: feature.geometry.coordinates[0],
        latitude: feature.geometry.coordinates[1],
        properties: feature.properties,
      });
    }
  };

  console.log("mapref", mapRef);

  return (
    <>
      <ControlPanel selectedDay={selectedDay} setSelectedDay={setSelectedDay} />

      <Map
        ref={mapRef}
        onClick={onClickMap}
        interactiveLayerIds={[
          "locations",
          "dayPoolTime-labels",
          "location-labels",
        ]}
        initialViewState={{
          longitude: -122.43623440090596,
          latitude: 37.73621337169021,
          zoom: 11.0,
        }}
        minZoom={11.0}
        style={{ height: "100vh", width: "100vw" }}
        mapStyle="https://wms.wheregroup.com/tileserver/style/osm-bright.json"
      >
        <Source type="geojson" data={geojson}>
          <Layer {...circleLayerStyle} />
          <Layer {...textLayerStyle} />
        </Source>
        {selectedDay && (
          <Source
            key={selectedDay}
            type="geojson"
            data={constructedLayers[selectedDay]}
          >
            <Layer {...timesLayerStyle} />
          </Source>
        )}
        <Source type="geojson" data={geojson}></Source>

        {/* Popup for Selected Location */}
        {popupInfo && (
          <SwimLocationPopup
            popupInfo={popupInfo}
            selectedDay={selectedDay}
            poolData={poolData}
            onClose={() => setPopupInfo(null)}
          />
        )}
      </Map>
    </>
  );
};

function createGoogleMapsLink(popupInfo) {
  let name = popupInfo.properties.name;
  if (name === "Hamilton Pool") {
    name = "Hamilton Aquatic Center (Hamilton Pool)";
  }
  const googleMapsString = `${name} ${popupInfo.properties.Address}`;
  const encodedAddress = encodeURIComponent(googleMapsString); // Ensure the address is URL-safe
  return `https://www.google.com/maps/search/?api=1&query=${googleMapsString}`;
}

const SwimLocationPopup = ({ popupInfo, selectedDay, poolData, onClose }) => {
  const poolName = popupInfo.properties.name as PoolEnum;
  const poolSchedule = poolData[poolName];
  const daySchedule = poolSchedule ? poolSchedule[selectedDay] : [];

  return (
    <Popup
      style={{ width: "350px", color: "black" }}
      className="popup-content"
      longitude={popupInfo.longitude}
      latitude={popupInfo.latitude}
      onClose={onClose}
      anchor="top"
    >
      <h3>
        {" "}
        <a href={popupInfo.properties.Website} target="_blank">
          {popupInfo.properties.name}
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            style={{ marginLeft: 5 }}
          >
            <path d="M18 13v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V10a2 2 0 0 1 2-2h6" />
            <polyline points="15 3 21 3 21 9" />
            <line x1="10" y1="14" x2="21" y2="3" />
          </svg>
        </a>
      </h3>
      <p>
        <a href={createGoogleMapsLink(popupInfo)} target="_blank">
          {popupInfo.properties.Address}{" "}
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            style={{ marginRight: 5 }}
          >
            <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
            <circle cx="12" cy="10" r="3" />
          </svg>
        </a>
      </p>

      {/* Detailed Schedule Section */}
      <div style={{ marginTop: "16px", borderTop: "1px solid #e5e7eb", paddingTop: "12px" }}>
        <h4 style={{ margin: "0 0 8px 0", fontSize: "14px", fontWeight: "600", color: "#374151" }}>
          {selectedDay} Schedule
        </h4>
        {daySchedule.length > 0 ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            {daySchedule.map((slot, index) => (
              <div
                key={index}
                style={{
                  padding: "8px 12px",
                  backgroundColor: slot.note.includes("Family Swim") ? "#dbeafe" : "#fef3c7",
                  borderRadius: "6px",
                  fontSize: "13px"
                }}
              >
                <div style={{ fontWeight: "600", color: "#1f2937" }}>
                  {slot.start} - {slot.end}
                </div>
                <div style={{
                  color: slot.note.includes("Family Swim") ? "#1d4ed8" : "#d97706",
                  fontSize: "12px",
                  marginTop: "2px"
                }}>
                  {slot.note}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p style={{ color: "#6b7280", fontSize: "13px", margin: 0 }}>
            No family swim times scheduled for {selectedDay}
          </p>
        )}
      </div>
    </Popup>
  );
};

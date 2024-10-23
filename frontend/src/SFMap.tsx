import React, { useEffect, useRef, useState } from "react";
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
import { PoolDictionary } from "./poolDataTypes";
import { daysOfWeek, generateGeoJSONLayers, getPoolSchedule } from "./utils";
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

const poolLocationStyle: SymbolLayer = {
  id: "locations",
  type: "symbol",
  layout: {
    "icon-image": "swimming",
    "icon-size": [
      "interpolate",
      // Set the exponential rate of change to 1.5
      ["exponential", 3.5],
      ["zoom"],
      // When zoom is 10, icon will be 50% size.
      10,
      0.1,
      // When zoom is 22, icon will be 10% size.
      22,
      0.01,
    ],

    "text-allow-overlap": true,
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
  const [selectedDay, setSelectedDay] = useState("");

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

  return (
    <>
      {/* <div className="header-banner">
        Family Swim SF Public Pools hours until August 10. Closed July 13.
      </div> */}
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
          longitude: -122.4323,
          latitude: 37.7612,
          zoom: 11.55,
        }}
        minZoom={11.55}
        style={{ height: "100vh", width: "100vw" }}
        maxBounds={[
          [-123.173825, 37.63983], // Southwest coordinates (min longitude, min latitude)
          [-122.28178, 37.929824], // Northeast coordinates (max longitude, max latitude)
        ]}
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

const SwimLocationPopup = ({ popupInfo, onClose }) => {
  const schedule = getPoolSchedule(popupInfo.properties.name, poolData);
  return (
    <Popup
      style={{ width: "300px", color: "black" }}
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
    </Popup>
  );
};

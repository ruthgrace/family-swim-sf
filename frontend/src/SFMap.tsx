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

import geojson from "../../map_data/public_pools.json";
import data from "../../map_data/family_swim_data_1728534973.2982707.json";
import { PoolDictionary } from "./poolDataTypes";
import { daysOfWeek, generateGeoJSONLayers } from "./utils";

const poolData = data as PoolDictionary;
const constructedLayers = generateGeoJSONLayers(geojson, poolData);

const circleLayerStyle: CircleLayer = {
  id: "locations",
  type: "circle",
  paint: {
    "circle-radius": 10,
    "circle-color": "#007cbf",
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
    "text-anchor": "top",
    "text-offset": [0, 1],
    "text-size": 12,
    "text-font": ["Open Sans Bold"],
    // "text-allow-overlap": true,
  },
};

const timesLayerStyle: SymbolLayer = {
  id: "dayPoolTime-labels",
  type: "symbol",
  layout: {
    "text-field": ["get", "label"],
    "text-anchor": "top",
    "text-offset": [0, 1],
    "text-size": 12,
    "text-font": ["Open Sans Bold"],
    // "text-allow-overlap": true,
  },
};

export const SFMap = () => {
  const mapRef = useRef<MapRef>(null);
  const [popupInfo, setPopupInfo] = useState(null);
  const [selectedDay, setSelectedDay] = useState("Monday");

  useEffect(() => {
    console.log("🚀 ~ useEffect ~ mapRef.current?:", mapRef.current);
    async function addImage() {
      if (!mapRef.current) return;
      const image = await mapRef.current.loadImage("/swimming.png");
      mapRef.current?.addImage("swimming", image.data);
    }
    if (!mapRef.current) return;
    addImage();
  }, [mapRef.current]);

  const onClickMap = (event: MapLayerMouseEvent) => {
    const features = event.features;
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
      <div
        style={{
          position: "absolute",
          top: 10,
          left: 10,
          zIndex: 1,
          background: "white",
          padding: "10px",
          color: "black",
        }}
      >
        {daysOfWeek.map((day) => {
          return (
            <div>
              <button onClick={() => setSelectedDay(day)}>{day}</button>
            </div>
          );
        })}
      </div>

      <Map
        ref={mapRef}
        onClick={onClickMap}
        interactiveLayerIds={["locations"]}
        initialViewState={{
          longitude: -122.4194,
          latitude: 37.7749,
          zoom: 13,
        }}
        style={{ height: "1000px", width: "1000px" }}
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
          <Popup
            style={{ width: "300px", color: "black" }}
            longitude={popupInfo.longitude}
            latitude={popupInfo.latitude}
            onClose={() => setPopupInfo(null)}
            anchor="top"
          >
            <h3>{popupInfo.properties.name}</h3>
            <p>{popupInfo.properties.Address}</p>
            {/* Display other details as needed */}
          </Popup>
        )}
      </Map>
    </>
  );
};

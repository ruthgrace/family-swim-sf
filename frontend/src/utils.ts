import { Pool, PoolDictionary, PoolEnum, Weekday } from "./poolDataTypes";
type GeoJSON = Record<string, Record<string, any>>;

export const daysOfWeek: Weekday[] = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

// Function to match and generate new GeoJSON layers for each day
export function generateGeoJSONLayers(
  geojson: GeoJSON,
  schedule: PoolDictionary
): GeoJSON {
  const layers: GeoJSON = {};

  // Initialize empty GeoJSON for each day
  daysOfWeek.forEach((day) => {
    layers[day] = {
      type: "FeatureCollection",
      features: [],
    };
  });

  // Loop through each pool in the GeoJSON
  geojson.features.forEach((feature: Record<string, any>) => {
    const poolName = feature.properties.name as PoolEnum;

    // If the pool has schedule data, add times for each day
    if (schedule[poolName]) {
      daysOfWeek.forEach((day) => {
        const swimTimes = schedule[poolName][day];

        // If there are swim times for this day, create a new feature for that day
        if (swimTimes.length > 0) {
          const times = swimTimes
            .map((time) => `${time.start} - ${time.end}`)
            .join("\n");
          const detailedTimes = swimTimes
            .map((time) => `${time.start} - ${time.end} (${time.note})`)
            .join("\n");

          const label = `${poolName}\n${times}`;

          const newFeature = {
            ...feature,
            properties: {
              ...feature.properties,
              times, // Add the times for this day
              detailedTimes,
              label,
            },
          };
          layers[day].features.push(newFeature);
        }
      });
    }
  });

  return layers;
}

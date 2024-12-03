import {
  Day,
  Pool,
  PoolDictionary,
  PoolEnum,
  ScheduleForPool,
  Weekday,
} from "./poolDataTypes";
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

          //   const label = `${poolName}\n${times}`;

          const newFeature = {
            ...feature,
            properties: {
              ...feature.properties,
              times, // Add the times for this day
              detailedTimes,
              //   label,
            },
          };
          layers[day].features.push(newFeature);
        }
      });
    }
  });

  return layers;
}

export function getPoolSchedule(
  poolName: PoolEnum,
  poolDictionary: PoolDictionary
): ScheduleForPool {
  const pool = poolDictionary[poolName];

  if (!pool) {
    throw new Error(`Pool ${poolName} not found.`);
  }

  const timeslots: { weekday: Weekday; times: string }[] = [];

  // Loop through each weekday and gather times
  for (const [weekday, dayEntries] of Object.entries(pool) as [
    Weekday,
    Day[]
  ][]) {
    dayEntries.forEach((entry) => {
      const time = `${entry.start} - ${entry.end}`;
      timeslots.push({ weekday, times: time });
    });
  }

  const grouped = timeslots.reduce((acc, entry) => {
    if (!acc[entry.weekday]) {
      acc[entry.weekday] = [];
    }
    acc[entry.weekday].push(entry.times);
    return acc;
  }, {} as ScheduleForPool);

  // Ensure all weekdays exist in the final structure
  daysOfWeek.forEach((day) => {
    if (!grouped[day]) {
      grouped[day] = ["N/A"];
    }
  });

  return grouped;
}

// Get the current Weekday
export function getCurrentWeekday(): Weekday {
  const today = new Date().getDay();
  // Mod and shift since 0 is Sunday for getDay()
  const correctIndex = (today + 6) % 7;

  return daysOfWeek[correctIndex];
}

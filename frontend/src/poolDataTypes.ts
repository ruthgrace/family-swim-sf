// generated with quicktype :P
export interface PoolDictionary {
  "Balboa Pool": Pool;
  "Coffman Pool": Pool;
  "Garfield Pool": Pool;
  "Hamilton Pool": Pool;
  "Martin Luther King Jr Pool": Pool;
  "Mission Community Pool": Pool;
  "North Beach Pool": Pool;
  "Rossi Pool": Pool;
  "Sava Pool": Pool;
}

export interface Pool {
  Saturday: Day[];
  Sunday: Day[];
  Monday: Day[];
  Tuesday: Day[];
  Wednesday: Day[];
  Thursday: Day[];
  Friday: Day[];
}

export interface Day {
  pool: PoolEnum;
  weekday: Weekday;
  start: string;
  end: string;
  note: Note;
}

export type ScheduleForPool = { weekday: Weekday; times: string }[];

export type Note =
  | "Parent Child Swim on Steps"
  | "Family Swim"
  | "Parent Child Swim"
  | "Family Swim in Small Pool";

export type PoolEnum =
  | "Balboa Pool"
  | "Coffman Pool"
  | "Garfield Pool"
  | "Hamilton Pool"
  | "Martin Luther King Jr Pool"
  | "Mission Community Pool"
  | "North Beach Pool"
  | "Rossi Pool"
  | "Sava Pool";

export type Weekday =
  | "Friday"
  | "Saturday"
  | "Thursday"
  | "Tuesday"
  | "Wednesday"
  | "Monday"
  | "Sunday";

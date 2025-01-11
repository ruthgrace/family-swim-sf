import { useState } from "react";
import { daysOfWeek } from "./utils";
import { Drawer } from "vaul";
import { Weekday } from "./poolDataTypes";

const snapPoints = ["245px", "350px"];

const updatedAt = "2025-01-10";

export const ControlPanel = ({
  selectedDay,
  setSelectedDay,
}: {
  selectedDay: Weekday;
  setSelectedDay: (day: Weekday) => void;
}) => {
  const [snap, setSnap] = useState<number | string | null>(snapPoints[0]);

  return (
    <>
      <div className="control-panel-style">
        <div className="mobile-only">
          <Drawer.Root
            defaultOpen={true}
            snapPoints={snapPoints}
            dismissible={false}
            activeSnapPoint={snap}
            setActiveSnapPoint={setSnap}
            modal={false}
          >
            <Drawer.Portal>
              {/* <Drawer.Overlay className="fixed inset-0 bg-black/40 mobile-only" /> */}

              <Drawer.Content
                data-testid="content"
                className="control-panel-style mobile-only fixed flex flex-col p-8 border border-gray-200 border-b-none rounded-t-[10px] bottom-0 left-0 right-0 h-full max-h-[97%] mx-[-1px]"
              >
                <Drawer.Handle />

                <div
                  style={{
                    paddingTop: "8px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 4,
                  }}
                >
                  <h2>Public Pool Family Swim Hours</h2>
                  <h3>Presented by Joyful Parenting SF and SF Kids Swim</h3>
                  <h5>Last updated {updatedAt}</h5>
                </div>
                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    paddingTop: 8,
                  }}
                >
                  {daysOfWeek.map((day) => {
                    return (
                      <div style={{ padding: 4 }}>
                        <button
                          className={`btn ${
                            day === selectedDay ? "btn-secondary" : ""
                          }`}
                          onClick={() => setSelectedDay(day)}
                        >
                          {day}
                        </button>
                      </div>
                    );
                  })}
                </div>
              </Drawer.Content>
            </Drawer.Portal>
          </Drawer.Root>
        </div>
      </div>
      <div className="desktop-only desktop-information-panel control-panel-style">
        <h2>Public Pool Family Swim Hours</h2>
        <h3>Presented by Joyful Parenting SF and SF Kids Swim</h3>
        <h5>Last updated {updatedAt}</h5>
      </div>
      <div className="desktop-only control-panel control-panel-style">
        {daysOfWeek.map((day) => {
          return (
            <div style={{ padding: 4 }}>
              <button
                className={`btn ${day === selectedDay ? "btn-secondary" : ""}`}
                onClick={() => setSelectedDay(day)}
              >
                {day}
              </button>
            </div>
          );
        })}
      </div>
    </>
  );
};

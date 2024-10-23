import { daysOfWeek } from "./utils";
import { Drawer } from "vaul";

export const ControlPanel = ({
  selectedDay,
  setSelectedDay,
}: {
  selectedDay: string;
  setSelectedDay: (day: string) => void;
}) => {
  return (
    <div className="control-panel">
      <Drawer.Root defaultOpen={true} open={true}>
        <Drawer.Portal>
          <Drawer.Trigger>Open</Drawer.Trigger>
          <Drawer.Content>
            <div>
              kajsdlfjasldf
              <div>askdjflaksjdf</div>
            </div>
            <Drawer.Title>Title</Drawer.Title>
          </Drawer.Content>
          <Drawer.Overlay />
        </Drawer.Portal>
      </Drawer.Root>

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
  );
};

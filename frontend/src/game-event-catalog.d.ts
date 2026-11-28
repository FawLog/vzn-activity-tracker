declare module "virtual:wos-event-catalog" {
  export const catalogVersion: string;
  export const stateTimeline: import("./lib/game-event-catalog").StateMilestone[];
  export const catalog: import("./lib/game-event-catalog").GameEventSummary[];
}

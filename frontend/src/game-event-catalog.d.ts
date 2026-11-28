declare module "virtual:wos-event-catalog" {
  export const catalogVersion: string;
  export const catalog: import("./lib/game-event-catalog").GameEventSummary[];
}

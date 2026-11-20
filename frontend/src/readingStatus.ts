import type { ReadingStatus } from "./api";

export const readingStatusLabels: Record<ReadingStatus, string> = {
  unread: "Unread",
  reading: "Reading",
  finished: "Finished",
};

export function pageLabel(start: number, end: number): string {
  return end === start ? `Page ${start}` : `Pages ${start}–${end}`;
}

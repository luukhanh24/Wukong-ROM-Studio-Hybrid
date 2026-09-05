export const LOG_PAGE_SIZE = 500;

export function mergeEvents(previous, incoming, limit = LOG_PAGE_SIZE) {
  const unique = new Map();
  for (const event of [...previous, ...incoming]) {
    const sequence = Number(event?.sequence || 0);
    unique.set(sequence > 0 ? sequence : JSON.stringify(event), event);
  }
  return [...unique.values()].sort((a, b) => Number(a.sequence || 0) - Number(b.sequence || 0)).slice(-limit);
}

export function eventCursor(events) {
  return events.reduce((max, event) => Math.max(max, Number(event.sequence) || 0), 0);
}

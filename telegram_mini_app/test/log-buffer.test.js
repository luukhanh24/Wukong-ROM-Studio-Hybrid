import { test } from "node:test";
import assert from "node:assert/strict";
import { mergeEvents, eventCursor } from "../lib/log-buffer.js";

test("10,000 events stay bounded, ordered and deduplicated without moving the cursor backwards", () => {
  let buffer = [];
  for (let sequence = 1; sequence <= 10000; sequence += 1) {
    buffer = mergeEvents(buffer, [{ sequence, type: "progress" }]);
  }
  assert.equal(buffer.length, 500);
  assert.equal(buffer[0].sequence, 9501);
  assert.equal(eventCursor(buffer), 10000);
  buffer = mergeEvents(buffer, [{ sequence: 10000 }, { sequence: 9900 }, { sequence: 1 }]);
  assert.equal(buffer.length, 500);
  assert.equal(buffer[0].sequence, 9501);
  assert.equal(eventCursor(buffer), 10000);
});

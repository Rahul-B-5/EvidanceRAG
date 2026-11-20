import {test} from "node:test";
import assert from "node:assert/strict";
import {readAnswerStream} from "../.test-build/answerStream.js";

function chunks(...parts) {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const part of parts) controller.enqueue(encoder.encode(part));
      controller.close();
    },
  });
}

test("Assistant stream handles chunk boundaries and heartbeats", async () => {
  const phases = [];
  await readAnswerStream(chunks('{"type":"progress","pha', 'se":"retrieving"}\n{"type":"heartbeat"}\n',
    '{"type":"progress","phase":"generating"}\n{"type":"answer","result":{}}\n'), phase => phases.push(phase));
  assert.deepEqual(phases, ["retrieving", "generating"]);
});

test("Assistant stream differentiates server errors from incomplete replies", async () => {
  await assert.rejects(readAnswerStream(chunks('{"type":"error","detail":"Provider unavailable"}\n'), () => {}),
    {message:"Provider unavailable"});
  await assert.rejects(readAnswerStream(chunks('{"type":"heartbeat"}\n'), () => {}),
    {message:"The answer stream ended before completion."});
});

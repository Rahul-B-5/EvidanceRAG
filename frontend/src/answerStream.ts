export type AssistantPhase = "retrieving" | "generating" | "saving";

export async function readAnswerStream(body: ReadableStream<Uint8Array>, onProgress: (phase: AssistantPhase) => void) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const {done, value} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {stream:true});
      if (buffer.length > 4_000_000) throw new Error("Assistant response exceeded the supported size.");
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line);
        if (event.type === "answer") return;
        if (event.type === "error") {
          throw new Error(typeof event.detail === "string" ? event.detail : "Unable to finish the answer.");
        }
        if (event.type === "progress" && ["retrieving", "generating", "saving"].includes(event.phase)) {
          onProgress(event.phase);
        }
      }
    }
    throw new Error("The answer stream ended before completion.");
  } finally {
    try { await reader.cancel(); } catch { /* The fetch may already be aborted. */ }
    reader.releaseLock();
  }
}

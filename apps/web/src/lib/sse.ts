// Lector de Server-Sent Events sobre fetch. EventSource no sirve aquí porque no
// admite POST ni cuerpo JSON.

export interface SSEEvent<T = unknown> {
  event: string;
  data: T;
}

export async function* readSSE(body: ReadableStream<Uint8Array>): AsyncGenerator<SSEEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }); // stream: no corta caracteres multibyte (tildes)
      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const raw = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        let event = "message";
        const dataLines: string[] = [];
        for (const line of raw.split("\n")) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
        }
        if (dataLines.length) yield { event, data: JSON.parse(dataLines.join("\n")) };
      }
    }
  } finally {
    reader.releaseLock();
  }
}

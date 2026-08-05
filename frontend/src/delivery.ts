export type ResponseDelivery = "complete" | "progressive";

export const DEFAULT_RESPONSE_DELIVERY: ResponseDelivery = "complete";
export const RESPONSE_DELIVERY_STORAGE_KEY = "archivist.answer-delivery.v1";
export const MAX_NDJSON_FRAME_CHARACTERS = 2_000_000;

type DeliveryStorage = Pick<Storage, "getItem" | "setItem">;

function browserStorage(): DeliveryStorage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function isResponseDelivery(value: unknown): value is ResponseDelivery {
  return value === "complete" || value === "progressive";
}

export function storedResponseDelivery(
  progressiveAvailable: boolean,
  storage: DeliveryStorage | null = browserStorage()
): ResponseDelivery {
  if (!progressiveAvailable || !storage) return DEFAULT_RESPONSE_DELIVERY;
  try {
    const stored = storage.getItem(RESPONSE_DELIVERY_STORAGE_KEY);
    return isResponseDelivery(stored) ? stored : DEFAULT_RESPONSE_DELIVERY;
  } catch {
    return DEFAULT_RESPONSE_DELIVERY;
  }
}

export function persistResponseDelivery(
  delivery: ResponseDelivery,
  progressiveAvailable: boolean,
  storage: DeliveryStorage | null = browserStorage()
) {
  if (!progressiveAvailable || !storage || !isResponseDelivery(delivery)) return;
  try {
    storage.setItem(RESPONSE_DELIVERY_STORAGE_KEY, delivery);
  } catch {
    // The selected delivery still applies to this page when storage is unavailable.
  }
}

export function progressiveElapsedSeconds(startedAtMs: number, observedAtMs: number) {
  if (!Number.isFinite(startedAtMs) || !Number.isFinite(observedAtMs)) return 0;
  return Math.max(0, Math.floor((observedAtMs - startedAtMs) / 1_000));
}

export function formatProgressiveElapsed(elapsedSeconds: number) {
  const bounded = Number.isFinite(elapsedSeconds)
    ? Math.max(0, Math.floor(elapsedSeconds))
    : 0;
  if (bounded < 1) return "just started";
  if (bounded < 60) return `${bounded}s elapsed`;
  const minutes = Math.floor(bounded / 60);
  const seconds = bounded % 60;
  return `${minutes}m ${seconds.toString().padStart(2, "0")}s elapsed`;
}

export async function readNdjson(
  stream: ReadableStream<Uint8Array>,
  onValue: (value: unknown) => void | Promise<void>
) {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const parseLine = async (line: string) => {
    if (line.length > MAX_NDJSON_FRAME_CHARACTERS) {
      throw new Error("Archivist received an oversized progressive response frame.");
    }
    const normalized = line.trim();
    if (!normalized) return;
    let value: unknown;
    try {
      value = JSON.parse(normalized);
    } catch {
      throw new Error("Archivist received a malformed progressive response frame.");
    }
    await onValue(value);
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      if (buffer.length > MAX_NDJSON_FRAME_CHARACTERS && !buffer.includes("\n")) {
        throw new Error("Archivist received an oversized progressive response frame.");
      }
      let newline = buffer.indexOf("\n");
      while (newline >= 0) {
        await parseLine(buffer.slice(0, newline).replace(/\r$/, ""));
        buffer = buffer.slice(newline + 1);
        newline = buffer.indexOf("\n");
      }
      if (buffer.length > MAX_NDJSON_FRAME_CHARACTERS) {
        throw new Error("Archivist received an oversized progressive response frame.");
      }
    }
    buffer += decoder.decode();
    await parseLine(buffer.replace(/\r$/, ""));
  } catch (error) {
    // Stop consuming the HTTP body when the protocol is already unusable.
    // This signals a disconnect promptly so the server can close its stream
    // half and eventually release the public concurrency lease. The paid
    // provider worker intentionally continues server-side for accounting.
    try {
      await reader.cancel(error);
    } catch {
      // Preserve the original parser/callback failure.
    }
    throw error;
  } finally {
    reader.releaseLock();
  }
}

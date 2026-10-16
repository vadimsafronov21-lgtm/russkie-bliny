export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code = "",
  ) {
    super(message);
  }
}
let csrf = "";
export function setCsrf(value: string) {
  csrf = value;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch("/api" + path, {
    credentials: "same-origin",
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrf,
      ...init.headers,
    },
  });
  const body = await response.json();
  if (!response.ok)
    throw new ApiError(
      body.detail?.message || "Не удалось выполнить запрос.",
      response.status,
      body.detail?.code,
    );
  return body as T;
}

export async function mutate<T>(path: string, body: unknown): Promise<T> {
  // Persist only an idempotency key and the operation signature, never credentials.
  // Retrying an uncertain result, including after refresh, must reuse the same key.
  const signature = "bliny-command:" + JSON.stringify([path, body]);
  const key = sessionStorage.getItem(signature) || crypto.randomUUID();
  sessionStorage.setItem(signature, key);
  try {
    const result = await api<T>(path, {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "Idempotency-Key": key },
    });
    sessionStorage.removeItem(signature);
    return result;
  } catch (error) {
    if (
      error instanceof ApiError &&
      error.status < 500 &&
      error.code !== "conflict"
    )
      sessionStorage.removeItem(signature);
    throw error;
  }
}

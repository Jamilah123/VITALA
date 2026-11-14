// Thin localStorage wrapper. Storage can be blocked or hold bad data, and the app
// must still work when it does.

export function readJson<T>(key: string): T | null {
  try {
    const text = localStorage.getItem(key);
    return text === null ? null : (JSON.parse(text) as T);
  } catch {
    return null;
  }
}

export function writeJson(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // The value simply lasts for this page load.
  }
}

export function removeKey(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch {
    // Nothing stored, nothing to remove.
  }
}

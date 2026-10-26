export interface StorageCheckResult {
  ok: boolean;

  // Basic debugging information, shown to the user when the check fails
  details: string[];
}

const PROBE_KEY = 'geo-ai-explorer-storage-probe';

function describe(error: unknown): string {
  if (error instanceof Error) {
    return error.name + ': ' + error.message;
  }

  return String(error);
}

function probe(getStorage: () => Storage): string | null {
  try {
    const storage = getStorage();
    const value = Date.now().toString();

    storage.setItem(PROBE_KEY, value);

    const read = storage.getItem(PROBE_KEY);

    storage.removeItem(PROBE_KEY);

    return read === value ? null : 'Value read back (' + read + ') did not match the value written (' + value + ')';
  }
  catch (error) {
    return describe(error);
  }
}

/**
 * Verifies that localStorage can be written to and read back. The application
 * keeps chat history and preferences there, which are lost without it.
 */
export function checkLocalStorage(): StorageCheckResult {
  const error = probe(() => window.localStorage);

  if (error == null) {
    return { ok: true, details: [] };
  }

  const sessionStorageError = probe(() => window.sessionStorage);

  return {
    ok: false,
    details: [
      'localStorage error: ' + error,
      'sessionStorage: ' + (sessionStorageError == null ? 'working' : sessionStorageError),
      'Cookies enabled: ' + navigator.cookieEnabled,
      'Origin: ' + window.location.origin,
      'Browser: ' + navigator.userAgent
    ]
  };
}

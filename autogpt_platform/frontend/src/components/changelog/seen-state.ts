// src/components/changelog/seen-state.ts

const STORAGE_KEY = "autogpt:changelog:lastSeenId";

export interface SeenStateAdapter {
  read(): Promise<string | null>;
  write(id: string): Promise<void>;
}

export const localStorageAdapter: SeenStateAdapter = {
  async read() {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch {
      return null;
    }
  },
  async write(id) {
    try {
      localStorage.setItem(STORAGE_KEY, id);
    } catch {
      // localStorage unavailable — accept the loss
    }
  },
};

interface UserPrefsAdapterOpts {
  endpoint?: string;
  fetchFn?: typeof fetch;
}

export function userPrefsAdapter(
  opts: UserPrefsAdapterOpts = {},
): SeenStateAdapter {
  const endpoint = opts.endpoint ?? "/api/me/preferences/changelog";
  const f = opts.fetchFn ?? fetch;

  const readCache = (): string | null => {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch {
      return null;
    }
  };
  const writeCache = (id: string): void => {
    try {
      localStorage.setItem(STORAGE_KEY, id);
    } catch {
      // ignore
    }
  };

  let cached = readCache();
  let revalidating = false;

  async function fetchRemote(): Promise<string | null> {
    const res = await f(endpoint, { credentials: "include" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const json = (await res.json()) as { lastSeenId?: string | null };
    return json.lastSeenId ?? null;
  }

  function revalidateInBackground() {
    if (revalidating) return;
    revalidating = true;
    fetchRemote()
      .then((remote) => {
        if (remote && remote !== cached) {
          cached = remote;
          writeCache(remote);
        }
      })
      .catch(() => {
        // offline / 5xx — keep cached value
      })
      .finally(() => {
        revalidating = false;
      });
  }

  return {
    async read() {
      if (cached !== null) {
        revalidateInBackground();
        return cached;
      }
      try {
        const remote = await fetchRemote();
        if (remote) {
          cached = remote;
          writeCache(remote);
        }
        return remote;
      } catch {
        return null;
      }
    },

    async write(id) {
      cached = id;
      writeCache(id);
      try {
        await f(endpoint, {
          method: "PUT",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ lastSeenId: id }),
        });
      } catch {
        // non-fatal — local cache persists, next session retries
      }
    },
  };
}

/**
 * Session persistence: chat history and the active image slots survive a
 * page reload via localStorage. Not real server-side session memory (the
 * backend is stateless per request, see App.jsx's buildQueryText) — this is
 * just so refreshing the tab doesn't throw away the conversation.
 */
const KEY = 'satquery.session.v1';

export function loadSession() {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function saveSession(session) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(session));
  } catch {
    // Storage full/unavailable (private browsing, etc.) -- non-fatal.
  }
}

export function clearSession() {
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    // ignore
  }
}

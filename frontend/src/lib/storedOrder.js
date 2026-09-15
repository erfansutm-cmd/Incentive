// Shared helper for the "top first" orders of the Final Decisions tab (the
// entity order and the plan type order).
//
// The order the user picked in the popup is remembered in the browser, so a
// reload does not undo it; *Reset to default* clears it and the configured
// default comes back. Storage can be unavailable (private mode, disabled
// cookies), in which case the order simply lives for the session.

export function readStoredOrder(key, fallback = []) {
  try {
    const raw = window.localStorage.getItem(key)
    if (!raw) return [...fallback]
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return [...fallback]
    const names = parsed.map((name) => String(name).trim()).filter(Boolean)
    return names.length ? names : [...fallback]
  } catch {
    return [...fallback]
  }
}

export function storeOrder(key, names) {
  try {
    window.localStorage.setItem(key, JSON.stringify([...names]))
  } catch {
    // not fatal: the order still applies to this session
  }
}

export function clearStoredOrder(key) {
  try {
    window.localStorage.removeItem(key)
  } catch {
    // nothing to clear
  }
}

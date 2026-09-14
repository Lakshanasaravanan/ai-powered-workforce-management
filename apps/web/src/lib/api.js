const base = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8001';
export async function request(path) { const r = await fetch(base + path); if (!r.ok)
    throw new Error('API unavailable'); return r.json(); }

import { createContext, useContext, useEffect, useState } from 'react';

const base = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8001';
type User = { id: string; full_name: string; role: string; employee_code: string; company_email: string; designation: string; department: string; manager_id: string | null };
type Auth = { user: User | null; loading: boolean; login: (employeeCode: string, password: string) => Promise<void>; logout: () => void };
const Context = createContext<Auth>(null!);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null); const [loading, setLoading] = useState(true);
  const logout = () => { sessionStorage.removeItem('infotech_token'); setUser(null); };
  useEffect(() => {
    const restore = async () => { const token = sessionStorage.getItem('infotech_token'); if (!token) { setLoading(false); return; } try { const response = await fetch(`${base}/api/v1/auth/me`, { headers: { Authorization: `Bearer ${token}` } }); if (!response.ok) throw new Error(); setUser(await response.json()); } catch { logout(); } finally { setLoading(false); } };
    void restore(); window.addEventListener('infotech:unauthorized', logout); return () => window.removeEventListener('infotech:unauthorized', logout);
  }, []);
  const login = async (employeeCode: string, password: string) => { const response = await fetch(`${base}/api/v1/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ employee_code: employeeCode, password }) }); if (!response.ok) throw new Error('Invalid credentials or unavailable API'); const payload = await response.json(); sessionStorage.setItem('infotech_token', payload.access_token); setUser(payload.employee); };
  return <Context.Provider value={{ user, loading, login, logout }}>{children}</Context.Provider>;
}
export const useAuth = () => useContext(Context);

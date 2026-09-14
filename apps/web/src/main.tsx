import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Link, Navigate, Route, Routes, useNavigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth';
import Employees from './Employees';
import './style.css';

const apiBase = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8001';

function Login() {
  const { login, user } = useAuth(); const go = useNavigate();
  const [employeeCode, setEmployeeCode] = useState(''); const [password, setPassword] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  if (user) return <Navigate to="/" replace />;
  return <main className="agent"><h1>InfoTech Workspace</h1><p className="muted">Sign in with your Employee ID</p><form className="card" onSubmit={async e => { e.preventDefault(); setBusy(true); setError(''); try { await login(employeeCode, password); go('/'); } catch { setError('Invalid credentials, inactive account, or unavailable API.'); } finally { setBusy(false); } }}><input aria-label="Employee ID" placeholder="Employee ID" value={employeeCode} onChange={e => setEmployeeCode(e.target.value)} required /><input aria-label="Password" type="password" placeholder="Password" value={password} onChange={e => setPassword(e.target.value)} required /><p className="muted">{error}</p><button disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button><p><Link to="/first-login">First time logging in?</Link></p></form></main>;
}

function FirstLogin() {
  const go = useNavigate(); const [employeeCode, setEmployeeCode] = useState(''); const [temporaryPassword, setTemporaryPassword] = useState(''); const [newPassword, setNewPassword] = useState(''); const [confirmPassword, setConfirmPassword] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  return <main className="agent"><h1>Activate your account</h1><form className="card" onSubmit={async e => { e.preventDefault(); if (!employeeCode || !temporaryPassword || !newPassword || newPassword !== confirmPassword) { setError('Complete all fields and ensure new passwords match.'); return; } setBusy(true); setError(''); try { const response = await fetch(`${apiBase}/api/v1/auth/first-login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ employee_code: employeeCode, temporary_password: temporaryPassword, new_password: newPassword }) }); if (!response.ok) throw Error(); go('/login', { state: { message: 'Account activated. Sign in with your new password.' } }); } catch { setError('Activation failed. Check your Employee ID and temporary password.'); } finally { setBusy(false); } }}><input aria-label="Employee ID" placeholder="Employee ID" value={employeeCode} onChange={e => setEmployeeCode(e.target.value)} required /><input aria-label="Temporary Password" type="password" placeholder="Temporary Password" value={temporaryPassword} onChange={e => setTemporaryPassword(e.target.value)} required /><input aria-label="New Password" type="password" placeholder="New Password" value={newPassword} onChange={e => setNewPassword(e.target.value)} required /><input aria-label="Confirm New Password" type="password" placeholder="Confirm New Password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} required /><p className="muted">{error}</p><button disabled={busy}>{busy ? 'Activating…' : 'Activate account'}</button></form></main>;
}

function Workspace() { const { user, logout } = useAuth(); return <main><h1>InfoTech Workspace</h1><p>Welcome, {user?.full_name}</p><button onClick={logout}>Logout</button></main>; }
function App() { const { user, loading } = useAuth(); if (loading) return <main>Restoring your session…</main>; if (!user) return <Routes><Route path="/login" element={<Login />} /><Route path="/first-login" element={<FirstLogin />} /><Route path="*" element={<Navigate to="/login" replace />} /></Routes>; return <Routes><Route path="/employees" element={user.role === 'ADMIN' ? <Employees /> : <Navigate to="/" replace />} /><Route path="*" element={<Workspace />} /></Routes>; }
createRoot(document.getElementById('root')!).render(<BrowserRouter><AuthProvider><App /></AuthProvider></BrowserRouter>);

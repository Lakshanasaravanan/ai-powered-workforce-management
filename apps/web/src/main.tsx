import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Link, NavLink, Navigate, Route, Routes, useNavigate } from 'react-router-dom';
import Agent from './Agent';
import { AuthProvider, useAuth } from './auth';
import Employees from './Employees';
import Inbox from './Inbox';
import Leave from './Leave';
import { notifications } from './lib/api';
import './style.css';

const emsBase = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8001';

function Login() {
  const { login, user } = useAuth();
  const navigate = useNavigate();
  const [employeeCode, setEmployeeCode] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to="/" replace />;
  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setBusy(true); setError('');
    try { await login(employeeCode, password); navigate('/'); }
    catch { setError('Invalid credentials, inactive account, or unavailable API.'); }
    finally { setBusy(false); }
  };
  return <main className="agent"><h1>InfoTech Workspace</h1><p className="muted">Sign in with your Employee ID</p><form className="card" onSubmit={submit}><label htmlFor="employee-code">Employee ID</label><input id="employee-code" value={employeeCode} onChange={(event) => setEmployeeCode(event.target.value)} required /><label htmlFor="password">Password</label><input id="password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required />{error && <p className="error" role="alert">{error}</p>}<button disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button><p><Link to="/first-login">First time logging in?</Link></p></form></main>;
}

function FirstLogin() {
  const navigate = useNavigate(); const [employeeCode, setEmployeeCode] = useState(''); const [temporaryPassword, setTemporaryPassword] = useState(''); const [newPassword, setNewPassword] = useState(''); const [confirmPassword, setConfirmPassword] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!employeeCode || !temporaryPassword || !newPassword || newPassword !== confirmPassword) { setError('Complete all fields and ensure new passwords match.'); return; }
    setBusy(true); setError('');
    try { const response = await fetch(`${emsBase}/api/v1/auth/first-login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ employee_code: employeeCode, temporary_password: temporaryPassword, new_password: newPassword }) }); if (!response.ok) throw new Error(); navigate('/login'); }
    catch { setError('Activation failed. Check your Employee ID and temporary password.'); }
    finally { setBusy(false); }
  };
  return <main className="agent"><h1>Activate your account</h1><form className="card" onSubmit={submit}><label htmlFor="first-code">Employee ID</label><input id="first-code" value={employeeCode} onChange={(event) => setEmployeeCode(event.target.value)} required /><label htmlFor="temporary-password">Temporary Password</label><input id="temporary-password" type="password" value={temporaryPassword} onChange={(event) => setTemporaryPassword(event.target.value)} required /><label htmlFor="new-password">New Password</label><input id="new-password" type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required /><label htmlFor="confirm-password">Confirm New Password</label><input id="confirm-password" type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} required />{error && <p className="error" role="alert">{error}</p>}<button disabled={busy}>{busy ? 'Activating…' : 'Activate account'}</button></form></main>;
}

function Home() { const { user } = useAuth(); return <main className="workspace-page"><p className="eyebrow">InfoTech Workspace</p><h1>Welcome, {user?.full_name}</h1><p className="muted">Use Leave to submit or review requests, Inbox to view notifications, and Agent for company-policy questions.</p></main>; }

function Workspace() {
  const { user, logout } = useAuth(); const [unread, setUnread] = useState(0);
  const refreshUnread = async () => { try { setUnread((await notifications.unreadCount()).unread_count); } catch { setUnread(0); } };
  useEffect(() => { void refreshUnread(); }, []);
  return <div className="app"><nav aria-label="Workspace navigation"><strong>IT</strong><NavLink to="/" end>Home</NavLink><NavLink to="/leave">Leave</NavLink><NavLink to="/inbox">Inbox{unread > 0 && <b className="badge">{unread}</b>}</NavLink><NavLink to="/agent">Agent</NavLink>{user?.role === 'ADMIN' && <NavLink to="/employees">Employees</NavLink>}<button className="logout" onClick={logout}>Logout</button></nav><div className="workspace-content"><Routes><Route path="/" element={<Home />} /><Route path="/leave" element={<Leave onNotificationChange={() => void refreshUnread()} />} /><Route path="/inbox" element={<Inbox onUnreadChange={() => void refreshUnread()} />} /><Route path="/agent" element={<Agent />} /><Route path="/employees" element={user?.role === 'ADMIN' ? <Employees /> : <Navigate to="/" replace />} /><Route path="*" element={<Navigate to="/" replace />} /></Routes></div></div>;
}

function App() { const { user, loading } = useAuth(); if (loading) return <main>Restoring your session…</main>; if (!user) return <Routes><Route path="/login" element={<Login />} /><Route path="/first-login" element={<FirstLogin />} /><Route path="*" element={<Navigate to="/login" replace />} /></Routes>; return <Workspace />; }

createRoot(document.getElementById('root')!).render(<BrowserRouter><AuthProvider><App /></AuthProvider></BrowserRouter>);

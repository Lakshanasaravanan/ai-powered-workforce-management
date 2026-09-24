import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Link, NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { ArrowRight, Bell, Bot, Building2, CalendarCheck, CalendarDays, ChevronRight, ClipboardList, Clock3, Eye, EyeOff, Inbox as InboxIcon, KeyRound, LayoutDashboard, LockKeyhole, LogOut, Menu, MessageCircle, RefreshCw, ShieldCheck, Users, X } from 'lucide-react';
import Agent from './Agent';
import Chat from './Chat';
import Calendar from './Calendar';
import { AuthProvider, useAuth } from './auth';
import Employees from './Employees';
import Inbox from './Inbox';
import Leave from './Leave';
import { calendar, leaves, notifications, type CalendarItem, type LeaveRequest, type Notification } from './lib/api';
import './style.css';

const emsBase = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8001';
const dateKey = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
const dateOnly = (value: string) => new Date(`${value.slice(0, 10)}T00:00:00`);
const labelRole = (role: string) => role[0] + role.slice(1).toLowerCase();

function Login() {
  const { login, user } = useAuth(); const navigate = useNavigate();
  const [companyEmail, setCompanyEmail] = useState(''); const [password, setPassword] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false); const [showPassword, setShowPassword] = useState(false);
  if (user) return <Navigate to="/" replace />;
  const submit = async (event: React.FormEvent<HTMLFormElement>) => { event.preventDefault(); setBusy(true); setError(''); try { await login(companyEmail, password); navigate('/'); } catch { setError('Invalid credentials, inactive account, or unavailable API.'); } finally { setBusy(false); } };
  return <main className="auth-page"><section className="auth-layout"><aside className="auth-brand-panel"><div className="auth-brand"><span><Building2 size={22} /></span><strong>InfoTech</strong></div><div><p className="eyebrow">Employee workspace</p><h1>One workspace for your workday.</h1><p>Access your workplace tools, company calendar, notifications, and authenticated assistance in one place.</p></div></aside><section className="auth-form-panel" aria-labelledby="sign-in-title"><div className="auth-form-heading"><span className="auth-form-icon"><LockKeyhole size={20} /></span><p className="eyebrow">Welcome back</p><h2 id="sign-in-title">Sign in to Workspace</h2><p>Use your company email and password to continue.</p></div><form onSubmit={submit}><label htmlFor="company-email">Company Email<input id="company-email" type="email" value={companyEmail} onChange={(event) => setCompanyEmail(event.target.value)} autoComplete="username" autoFocus disabled={busy} required /></label><label htmlFor="password">Password<span className="auth-password-field"><input id="password" type={showPassword ? 'text' : 'password'} value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" disabled={busy} /><button type="button" className="password-toggle" aria-label={showPassword ? 'Hide password' : 'Show password'} onClick={() => setShowPassword((visible) => !visible)} disabled={busy}>{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button></span></label>{error && <p className="error" role="alert">{error}</p>}<button className="auth-submit" disabled={busy}>{busy ? <><RefreshCw size={16} className="spin" /> Signing in</> : <>Sign in <ArrowRight size={16} /></>}</button></form><div className="auth-first-login"><KeyRound size={17} aria-hidden="true" /><div><strong>First time logging in?</strong><Link to="/first-login">Activate your account</Link></div></div></section></section></main>;
}

function FirstLogin() {
  const navigate = useNavigate();
  const [employeeCode, setEmployeeCode] = useState('');
  const [temporaryPassword, setTemporaryPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [showTemporaryPassword, setShowTemporaryPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!employeeCode || !temporaryPassword || !newPassword || newPassword !== confirmPassword) {
      setError('Complete all fields and ensure new passwords match.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const response = await fetch(`${emsBase}/api/v1/auth/first-login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ employee_code: employeeCode, temporary_password: temporaryPassword, new_password: newPassword }) });
      if (!response.ok) throw new Error();
      navigate('/login');
    } catch {
      setError('Activation failed. Check your Employee ID and temporary password.');
    } finally {
      setBusy(false);
    }
  };
  return <main className="auth-page"><section className="auth-layout activation-layout"><aside className="auth-brand-panel"><div className="auth-brand"><span><Building2 size={22} /></span><strong>InfoTech</strong></div><div><p className="eyebrow">Account activation</p><h1>Set up your Workspace access.</h1><p>Use the temporary credential supplied for your account, then choose a password for future sign-ins.</p></div><div className="auth-security-note"><ShieldCheck size={18} aria-hidden="true" /><span>Temporary credentials are used only to activate your account.</span></div></aside><section className="auth-form-panel" aria-labelledby="activation-title"><div className="auth-form-heading"><span className="auth-form-icon"><KeyRound size={20} /></span><p className="eyebrow">First-time access</p><h2 id="activation-title">Activate your account</h2><p>Create the password you will use to sign in to InfoTech Workspace.</p></div><form onSubmit={submit}><label htmlFor="first-code">Employee ID<input id="first-code" value={employeeCode} onChange={(event) => setEmployeeCode(event.target.value)} autoComplete="username" autoFocus disabled={busy} required /></label><label htmlFor="temporary-password">Temporary password<span className="auth-password-field"><input id="temporary-password" type={showTemporaryPassword ? 'text' : 'password'} value={temporaryPassword} onChange={(event) => setTemporaryPassword(event.target.value)} autoComplete="one-time-code" disabled={busy} required /><button type="button" className="password-toggle" aria-label={showTemporaryPassword ? 'Hide temporary password' : 'Show temporary password'} onClick={() => setShowTemporaryPassword((visible) => !visible)} disabled={busy}>{showTemporaryPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button></span></label><label htmlFor="new-password">New password<span className="auth-password-field"><input id="new-password" type={showNewPassword ? 'text' : 'password'} value={newPassword} onChange={(event) => setNewPassword(event.target.value)} autoComplete="new-password" disabled={busy} required /><button type="button" className="password-toggle" aria-label={showNewPassword ? 'Hide new password' : 'Show new password'} onClick={() => setShowNewPassword((visible) => !visible)} disabled={busy}>{showNewPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button></span></label><label htmlFor="confirm-password">Confirm new password<span className="auth-password-field"><input id="confirm-password" type={showConfirmPassword ? 'text' : 'password'} value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} autoComplete="new-password" disabled={busy} required /><button type="button" className="password-toggle" aria-label={showConfirmPassword ? 'Hide confirm password' : 'Show confirm password'} onClick={() => setShowConfirmPassword((visible) => !visible)} disabled={busy}>{showConfirmPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button></span></label>{error && <p className="error" role="alert">{error}</p>}<button className="auth-submit" disabled={busy}>{busy ? <><RefreshCw size={16} className="spin" /> Activating</> : <>Activate account <ArrowRight size={16} /></>}</button></form><p className="auth-back-link"><Link to="/login">Back to sign in</Link></p></section></section></main>;
}

function DashboardCard({ title, icon, action, children }: { title: string; icon: ReactNode; action?: ReactNode; children: ReactNode }) {
  return <section className="dashboard-card"><header className="dashboard-card-header"><div><span className="card-icon" aria-hidden="true">{icon}</span><h2>{title}</h2></div>{action}</header>{children}</section>;
}

function DashboardSkeleton({ lines }: { lines: number }) {
  return <div className="dashboard-skeleton" aria-label="Loading dashboard data">{Array.from({ length: lines }, (_, index) => <span key={index} />)}</div>;
}

function WidgetError({ onRetry }: { onRetry: () => void }) {
  return <div className="widget-error"><p>Unable to load this information.</p><button className="button-secondary button-small" type="button" onClick={() => void onRetry()}><RefreshCw size={14} aria-hidden="true" /> Try again</button></div>;
}

function EmptyState({ icon, message, action }: { icon: ReactNode; message: string; action?: ReactNode }) {
  return <div className="empty-state"><span aria-hidden="true">{icon}</span><p>{message}</p>{action && <div>{action}</div>}</div>;
}

function Home() {
  const { user } = useAuth();
  const [leaveItems, setLeaveItems] = useState<LeaveRequest[]>([]);
  const [calendarItems, setCalendarItems] = useState<CalendarItem[]>([]);
  const [notificationItems, setNotificationItems] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState<Record<string, boolean>>({});
  const load = async () => {
    setLoading(true);
    const today = new Date();
    const future = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 30);
    const [leaveResult, calendarResult, notificationResult] = await Promise.allSettled([leaves.mine(), calendar.feed(dateKey(today), dateKey(future)), notifications.list()]);
    const nextErrors: Record<string, boolean> = {};
    if (leaveResult.status === 'fulfilled') setLeaveItems(leaveResult.value); else nextErrors.leave = true;
    if (calendarResult.status === 'fulfilled') setCalendarItems(calendarResult.value); else nextErrors.calendar = true;
    if (notificationResult.status === 'fulfilled') setNotificationItems(notificationResult.value); else nextErrors.notifications = true;
    setErrors(nextErrors);
    setLoading(false);
  };
  useEffect(() => { void load(); }, []);
  const pendingLeaves = leaveItems.filter((item) => item.status === 'PENDING');
  const recentLeaves = [...leaveItems].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, 3);
  const upcoming = useMemo(() => [...calendarItems].sort((a, b) => a.start_at.localeCompare(b.start_at)).slice(0, 4), [calendarItems]);
  const unread = notificationItems.filter((item) => !item.is_read).length;
  const greetings = new Date().getHours() < 12 ? 'Good morning' : new Date().getHours() < 18 ? 'Good afternoon' : 'Good evening';

  return <main className="workspace-page dashboard-page">
    <header className="page-header dashboard-header"><div><p className="eyebrow">Your workspace</p><h1>{greetings}, {user?.full_name?.split(' ')[0] ?? 'there'}.</h1><p className="muted">Here is a focused view of what needs your attention.</p></div><div className="identity-summary" aria-label="Your workplace identity"><span className="role-badge">{labelRole(user?.role ?? 'EMPLOYEE')}</span><span>{user?.designation || 'InfoTech employee'}</span></div></header>
    <section className="quick-actions" aria-label="Quick actions">
      <Link className="quick-action" to="/leave"><ClipboardList aria-hidden="true" /><span><strong>Request leave</strong><small>Submit and track requests</small></span><ChevronRight aria-hidden="true" /></Link>
      <Link className="quick-action" to="/agent"><Bot aria-hidden="true" /><span><strong>Ask the agent</strong><small>Find policy guidance</small></span><ChevronRight aria-hidden="true" /></Link>
      <Link className="quick-action" to="/chat"><MessageCircle aria-hidden="true" /><span><strong>Open chat</strong><small>Continue a conversation</small></span><ChevronRight aria-hidden="true" /></Link>
      <Link className="quick-action" to="/calendar"><CalendarDays aria-hidden="true" /><span><strong>View calendar</strong><small>See upcoming work</small></span><ChevronRight aria-hidden="true" /></Link>
    </section>
    <section className="dashboard-grid">
      <DashboardCard title="Leave overview" icon={<ClipboardList size={18} />} action={<Link className="text-link" to="/leave">View leave</Link>}>{loading ? <DashboardSkeleton lines={3} /> : errors.leave ? <WidgetError onRetry={load} /> : <><div className="dashboard-stat"><strong>{pendingLeaves.length}</strong><span>pending request{pendingLeaves.length === 1 ? '' : 's'}</span></div>{recentLeaves.length ? <ul className="compact-list">{recentLeaves.map((leave) => <li key={leave.id}><div><strong>{leave.leave_type.replace('_', ' ').toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase())}</strong><small>{dateOnly(leave.start_date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}{leave.end_date !== leave.start_date ? ` – ${dateOnly(leave.end_date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}` : ''}</small></div><span className={`status status-${leave.status.toLowerCase()}`}>{leave.status.toLowerCase()}</span></li>)}</ul> : <EmptyState icon={<ClipboardList size={20} />} message="No leave requests yet." action={<Link to="/leave">Request leave</Link>} />}</>}</DashboardCard>
      <DashboardCard title="Upcoming" icon={<CalendarDays size={18} />} action={<Link className="text-link" to="/calendar">Full calendar</Link>}>{loading ? <DashboardSkeleton lines={3} /> : errors.calendar ? <WidgetError onRetry={load} /> : upcoming.length ? <ul className="compact-list upcoming-list">{upcoming.map((item) => <li key={`${item.kind}-${item.id}`}><span className={`event-dot ${item.kind === 'LEAVE' ? 'leave-dot' : ''}`} aria-hidden="true" /><div><strong>{item.kind === 'LEAVE' ? 'Approved leave' : item.title}</strong><small>{item.all_day ? dateOnly(item.start_at).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' }) : new Date(item.start_at).toLocaleString(undefined, { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</small></div></li>)}</ul> : <EmptyState icon={<CalendarCheck size={20} />} message="Nothing scheduled in the next 30 days." action={<Link to="/calendar">Open calendar</Link>} />}</DashboardCard>
      <DashboardCard title="Inbox" icon={<InboxIcon size={18} />} action={<Link className="text-link" to="/inbox">Open inbox</Link>}>{loading ? <DashboardSkeleton lines={3} /> : errors.notifications ? <WidgetError onRetry={load} /> : notificationItems.length ? <><div className="dashboard-stat"><strong>{unread}</strong><span>unread notification{unread === 1 ? '' : 's'}</span></div><ul className="compact-list notification-preview">{notificationItems.slice(0, 3).map((item) => <li key={item.id}><span className={`unread-indicator ${item.is_read ? 'read' : ''}`} aria-hidden="true" /><div><strong>{item.title}</strong><small>{item.message}</small></div></li>)}</ul></> : <EmptyState icon={<Bell size={20} />} message="You are all caught up." action={<Link to="/inbox">Open inbox</Link>} />}</DashboardCard>
      <DashboardCard title="Your workspace" icon={<Users size={18} />}><dl className="profile-facts"><div><dt>Employee ID</dt><dd>{user?.employee_code}</dd></div><div><dt>Department</dt><dd>{user?.department || 'Not specified'}</dd></div><div><dt>Role</dt><dd>{labelRole(user?.role ?? 'EMPLOYEE')}</dd></div><div><dt>Designation</dt><dd>{user?.designation || 'Not specified'}</dd></div></dl></DashboardCard>
    </section>
  </main>;
}

type NavigationItem = { to: string; label: string; icon: typeof LayoutDashboard; adminOnly?: boolean };
const navigation: NavigationItem[] = [
  { to: '/', label: 'Home', icon: LayoutDashboard },
  { to: '/chat', label: 'Chat', icon: MessageCircle },
  { to: '/calendar', label: 'Calendar', icon: CalendarDays },
  { to: '/leave', label: 'Leave', icon: ClipboardList },
  { to: '/inbox', label: 'Inbox', icon: Bell },
  { to: '/agent', label: 'Agent', icon: Bot },
  { to: '/employees', label: 'Employees', icon: Users, adminOnly: true },
];

function Workspace() {
  const { user, logout } = useAuth();
  const [unread, setUnread] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  const refreshUnread = async () => {
    try { setUnread((await notifications.unreadCount()).unread_count); } catch { setUnread(0); }
  };
  useEffect(() => { void refreshUnread(); }, []);
  useEffect(() => { setMenuOpen(false); }, [location.pathname]);
  return <div className="app-shell">
    <button className="mobile-menu-button" type="button" aria-label={menuOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={menuOpen} onClick={() => setMenuOpen((open) => !open)}>{menuOpen ? <X /> : <Menu />}</button>
    <aside className={`workspace-sidebar ${menuOpen ? 'is-open' : ''}`} aria-label="Workspace navigation"><div className="brand"><span className="brand-mark" aria-hidden="true">IT</span><div><strong>InfoTech</strong><small>Workspace</small></div></div><nav className="primary-navigation" aria-label="Primary">{navigation.filter((item) => !item.adminOnly || user?.role === 'ADMIN').map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} end={to === '/'}><Icon size={19} aria-hidden="true" /><span>{label}</span>{to === '/inbox' && unread > 0 && <b className="badge">{unread > 99 ? '99+' : unread}</b>}</NavLink>)}</nav><div className="sidebar-footer"><div className="sidebar-profile"><span className="profile-avatar" aria-hidden="true">{user?.full_name?.split(' ').map((part) => part[0]).join('').slice(0, 2) || 'IT'}</span><div><strong>{user?.full_name}</strong><small>{user?.employee_code}</small><span className="role-badge">{labelRole(user?.role ?? 'EMPLOYEE')}</span></div></div><button className="sidebar-logout" type="button" onClick={logout}><LogOut size={17} aria-hidden="true" /> <span>Log out</span></button></div></aside>
    {menuOpen && <button className="navigation-backdrop" type="button" aria-label="Close navigation" onClick={() => setMenuOpen(false)} />}
    <div className="workspace-content"><Routes><Route path="/" element={<Home />} /><Route path="/chat" element={<Chat />} /><Route path="/calendar" element={<Calendar />} /><Route path="/leave" element={<Leave onNotificationChange={() => void refreshUnread()} />} /><Route path="/inbox" element={<Inbox onUnreadChange={() => void refreshUnread()} />} /><Route path="/agent" element={<Agent />} /><Route path="/employees" element={user?.role === 'ADMIN' ? <Employees /> : <Navigate to="/" replace />} /><Route path="*" element={<Navigate to="/" replace />} /></Routes></div>
  </div>;
}

function App() {
  const { user, loading } = useAuth();
  if (loading) return <main className="session-loading"><Clock3 aria-hidden="true" /><p>Restoring your session…</p></main>;
  if (!user) return <Routes><Route path="/login" element={<Login />} /><Route path="/first-login" element={<FirstLogin />} /><Route path="*" element={<Navigate to="/login" replace />} /></Routes>;
  return <Workspace />;
}

createRoot(document.getElementById('root')!).render(<BrowserRouter><AuthProvider><App /></AuthProvider></BrowserRouter>);

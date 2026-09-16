import { useEffect, useState } from 'react';
import { ApiError, type Notification, notifications } from './lib/api';

type Props = { onUnreadChange: () => void };
const labels = { LEAVE: 'Leave', CHAT: 'Chat', CALENDAR: 'Calendar', SYSTEM: 'System' };
function message(error: unknown) { return error instanceof ApiError && error.status === 403 ? 'You are not authorized to access that notification.' : 'Unable to load notifications. Please try again.'; }

export default function Inbox({ onUnreadChange }: Props) {
  const [items, setItems] = useState<Notification[]>([]); const [loading, setLoading] = useState(true); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const load = async () => { setLoading(true); setError(''); try { setItems(await notifications.list()); } catch (caught) { setError(message(caught)); } finally { setLoading(false); } };
  useEffect(() => { void load(); onUnreadChange(); }, []);
  const markRead = async (item: Notification) => { if (item.is_read) return; try { const updated = await notifications.markRead(item.id); setItems(current => current.map(existing => existing.id === updated.id ? updated : existing)); onUnreadChange(); } catch (caught) { setError(message(caught)); } };
  const markAll = async () => { setBusy(true); try { await notifications.markAllRead(); setItems(current => current.map(item => ({ ...item, is_read: true, read_at: item.read_at ?? new Date().toISOString() }))); onUnreadChange(); } catch (caught) { setError(message(caught)); } finally { setBusy(false); } };
  return <main className="workspace-page"><header><div><p className="eyebrow">Personal inbox</p><h1>Inbox</h1></div><div><button className="ghost" onClick={() => void load()} disabled={loading}>Refresh</button><button onClick={() => void markAll()} disabled={busy || !items.some(item => !item.is_read)}>{busy ? 'Updating…' : 'Mark all as read'}</button></div></header>{error && <p className="error" role="alert">{error}</p>}{loading ? <p className="muted">Loading notifications…</p> : !items.length ? <section className="card"><h2>All caught up</h2><p className="muted">Your notifications will appear here.</p></section> : <section className="inbox-list">{items.map(item => <button className={`notification ${item.is_read ? 'read' : 'unread'}`} key={item.id} onClick={() => void markRead(item)} aria-label={`${item.is_read ? 'Read' : 'Unread'} ${item.title}`}><span className="category">{labels[item.category]}</span><strong>{item.title}</strong><p>{item.message}</p><small>{new Date(item.created_at).toLocaleString()} · {item.is_read ? 'Read' : 'Unread'}</small></button>)}</section>}</main>;
}

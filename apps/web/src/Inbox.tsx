import { useEffect, useMemo, useState } from 'react';
import { Bell, CalendarDays, CheckCheck, CircleAlert, ClipboardList, Inbox as InboxIcon, MessageCircle, RefreshCw, Settings2 } from 'lucide-react';
import { ApiError, type Notification, notifications } from './lib/api';

type Props = { onUnreadChange: () => void };

const labels: Record<Notification['category'], string> = { LEAVE: 'Leave', CHAT: 'Chat', CALENDAR: 'Calendar', SYSTEM: 'System' };

function notificationIcon(category: Notification['category']) {
  if (category === 'LEAVE') return <ClipboardList size={18} />;
  if (category === 'CHAT') return <MessageCircle size={18} />;
  if (category === 'CALENDAR') return <CalendarDays size={18} />;
  return <Settings2 size={18} />;
}

function apiMessage(error: unknown): string {
  return error instanceof ApiError && error.status === 403
    ? 'You are not authorized to access that notification.'
    : 'Unable to load notifications. Please try again.';
}

function timestamp(value: string): string {
  const date = new Date(value);
  const today = new Date();
  if (date.toDateString() === today.toDateString()) return date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: date.getFullYear() !== today.getFullYear() ? 'numeric' : undefined });
}

function InboxLoading() {
  return <div className="inbox-loading" aria-label="Loading notifications"><span /><span /><span /><span /></div>;
}

export default function Inbox({ onUnreadChange }: Props) {
  const [items, setItems] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const unread = useMemo(() => items.filter((item) => !item.is_read).length, [items]);

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      setItems(await notifications.list());
    } catch (caught) {
      setError(apiMessage(caught));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    onUnreadChange();
  }, []);

  const markRead = async (item: Notification) => {
    if (item.is_read || busy) return;
    setBusy(true);
    try {
      const updated = await notifications.markRead(item.id);
      setItems((current) => current.map((existing) => existing.id === updated.id ? updated : existing));
      onUnreadChange();
    } catch (caught) {
      setError(apiMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  const markAll = async () => {
    if (!unread || busy) return;
    setBusy(true);
    setError('');
    try {
      await notifications.markAllRead();
      setItems((current) => current.map((item) => ({ ...item, is_read: true, read_at: item.read_at ?? new Date().toISOString() })));
      onUnreadChange();
    } catch (caught) {
      setError(apiMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  return <main className="workspace-page inbox-workspace"><header className="page-header inbox-page-header"><div><p className="eyebrow">Personal inbox</p><h1>Inbox</h1><p className="muted">{loading ? 'Loading notifications…' : unread ? String(unread) + ' unread notification' + (unread === 1 ? '' : 's') : 'You are all caught up.'}</p></div><div><button type="button" className="button-secondary" disabled={loading} onClick={() => void load()}><RefreshCw size={16} className={loading ? 'spin' : ''} /> Refresh</button><button type="button" disabled={busy || !unread} onClick={() => void markAll()}><CheckCheck size={16} /> {busy ? 'Updating…' : 'Mark all read'}</button></div></header>
    {error && <div className="inbox-error error" role="alert"><CircleAlert size={17} /><span>{error}</span><button type="button" className="button-secondary button-small" onClick={() => void load()}>Try again</button></div>}
    <section className="notification-center" aria-label="Notifications">{loading ? <InboxLoading /> : !items.length ? <div className="inbox-empty-state"><span><InboxIcon size={28} /></span><h2>Nothing in your inbox</h2><p>Notifications about your workplace activity will appear here.</p></div> : <div className="notification-list">{items.map((item) => <article className={'notification-card ' + (item.is_read ? 'read' : 'unread')} key={item.id}><span className="notification-type-icon" aria-hidden="true">{notificationIcon(item.category)}</span><div className="notification-content"><div className="notification-meta"><span className="notification-category">{labels[item.category]}</span>{!item.is_read && <span className="unread-label"><Bell size={11} /> Unread</span>}<time dateTime={item.created_at}>{timestamp(item.created_at)}</time></div><h2>{item.title}</h2><p>{item.message}</p></div>{!item.is_read && <button className="mark-read-button button-secondary button-small" type="button" disabled={busy} onClick={() => void markRead(item)}>Mark read</button>}</article>)}</div>}</section>
  </main>;
}

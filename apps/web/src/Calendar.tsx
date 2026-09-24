import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { CalendarDays, ChevronLeft, ChevronRight, CircleAlert, Clock3, Edit3, MapPin, Plus, RefreshCw, Trash2, X } from 'lucide-react';
import { calendar, type CalendarItem } from './lib/api';
import { useAuth } from './auth';

type Dialog = 'create' | 'edit' | 'delete' | null;
type EventFormValue = { title: string; description: string; eventType: string; start: string; end: string; allDay: boolean; location: string };

const eventTypes = ['MEETING', 'TRAINING', 'COMPANY_EVENT', 'HOLIDAY', 'GENERAL'];
const weekdays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const dayKey = (date: Date) => String(date.getFullYear()) + '-' + String(date.getMonth() + 1).padStart(2, '0') + '-' + String(date.getDate()).padStart(2, '0');
const dateOnly = (value: string) => new Date(value.slice(0, 10) + 'T00:00:00');
const typeLabel = (value: string) => value.replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
const isEvent = (item: CalendarItem | null): item is CalendarItem => !!item && item.kind === 'EVENT';

function itemStartKey(item: CalendarItem): string {
  return item.all_day ? item.start_at.slice(0, 10) : dayKey(new Date(item.start_at));
}

function itemEndKey(item: CalendarItem): string {
  return item.all_day ? item.end_at.slice(0, 10) : dayKey(new Date(item.end_at));
}

function intersects(item: CalendarItem, date: string): boolean {
  return itemStartKey(item) <= date && itemEndKey(item) >= date;
}

function localInput(value: string, allDay: boolean): string {
  if (allDay) return value.slice(0, 10);
  const date = new Date(value);
  return String(date.getFullYear()) + '-' + String(date.getMonth() + 1).padStart(2, '0') + '-' + String(date.getDate()).padStart(2, '0') + 'T' + String(date.getHours()).padStart(2, '0') + ':' + String(date.getMinutes()).padStart(2, '0');
}

function payloadDate(value: string, allDay: boolean): string {
  return allDay ? value + 'T00:00:00' : value;
}

function itemTime(item: CalendarItem): string {
  if (item.all_day) return 'All day';
  return new Date(item.start_at).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
}

function itemRange(item: CalendarItem): string {
  const start = item.all_day ? dateOnly(item.start_at) : new Date(item.start_at);
  const end = item.all_day ? dateOnly(item.end_at) : new Date(item.end_at);
  const startText = start.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  const endText = end.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  if (item.all_day) return startText === endText ? 'All day · ' + startText : 'All day · ' + startText + ' – ' + endText;
  const startTime = start.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
  const endTime = end.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
  return startText === endText ? startText + ' · ' + startTime + ' – ' + endTime : startText + ' ' + startTime + ' – ' + endText + ' ' + endTime;
}

function EventPill({ item, onSelect }: { item: CalendarItem; onSelect: () => void }) {
  return <button type="button" className={'calendar-event-pill ' + (item.kind === 'LEAVE' ? 'leave' : '')} onClick={(event) => { event.stopPropagation(); onSelect(); }} title={item.kind === 'LEAVE' ? 'Approved leave' : item.title}><span>{item.kind === 'LEAVE' ? 'Leave' : itemTime(item)}</span><strong>{item.kind === 'LEAVE' ? 'Approved leave' : item.title}</strong></button>;
}

function CalendarForm({ item, selectedDate, busy, error, onSubmit, onClose }: { item?: CalendarItem; selectedDate: string; busy: boolean; error: string; onSubmit: (value: EventFormValue) => void; onClose: () => void }) {
  const initialAllDay = item?.all_day ?? false;
  const [allDay, setAllDay] = useState(initialAllDay);
  const [title, setTitle] = useState(item?.title ?? '');
  const [description, setDescription] = useState(item?.description ?? '');
  const [eventType, setEventType] = useState(item?.event_type ?? 'GENERAL');
  const [start, setStart] = useState(item ? localInput(item.start_at, item.all_day) : initialAllDay ? selectedDate : selectedDate + 'T00:00');
  const [end, setEnd] = useState(item ? localInput(item.end_at, item.all_day) : initialAllDay ? selectedDate : selectedDate + 'T00:00');
  const [location, setLocation] = useState(item?.location ?? '');
  const [validation, setValidation] = useState('');

  const switchAllDay = (value: boolean) => {
    setAllDay(value);
    if (value) {
      setStart(start.slice(0, 10));
      setEnd(end.slice(0, 10));
    } else {
      setStart(start.length === 10 ? start + 'T00:00' : start);
      setEnd(end.length === 10 ? end + 'T00:00' : end);
    }
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!title.trim() || !start || !end) {
      setValidation('Add a title, start, and end.');
      return;
    }
    if (end < start) {
      setValidation('End must not be before start.');
      return;
    }
    setValidation('');
    onSubmit({ title: title.trim(), description: description.trim(), eventType, start: payloadDate(start, allDay), end: payloadDate(end, allDay), allDay, location: location.trim() });
  };

  return <form className="calendar-event-form" onSubmit={submit}><div className="calendar-form-grid"><label htmlFor="calendar-title">Title<input id="calendar-title" value={title} onChange={(event) => setTitle(event.target.value)} maxLength={200} disabled={busy} required autoFocus /></label><label htmlFor="calendar-type">Event type<select id="calendar-type" value={eventType} onChange={(event) => setEventType(event.target.value)} disabled={busy}>{eventTypes.map((type) => <option key={type} value={type}>{typeLabel(type)}</option>)}</select></label><label htmlFor="calendar-start">Start<input id="calendar-start" type={allDay ? 'date' : 'datetime-local'} value={start} onChange={(event) => setStart(event.target.value)} disabled={busy} required /></label><label htmlFor="calendar-end">End<input id="calendar-end" type={allDay ? 'date' : 'datetime-local'} min={start || undefined} value={end} onChange={(event) => setEnd(event.target.value)} disabled={busy} required /></label><label className="calendar-all-day" htmlFor="calendar-all-day"><input id="calendar-all-day" type="checkbox" checked={allDay} onChange={(event) => switchAllDay(event.target.checked)} disabled={busy} /> All-day event</label><label htmlFor="calendar-location">Location <span>(optional)</span><input id="calendar-location" value={location} onChange={(event) => setLocation(event.target.value)} maxLength={200} disabled={busy} /></label><label className="calendar-description" htmlFor="calendar-description">Description <span>(optional)</span><textarea id="calendar-description" value={description} onChange={(event) => setDescription(event.target.value)} maxLength={5000} disabled={busy} /></label></div>{(validation || error) && <p className="error" role="alert">{validation || error}</p>}<div className="calendar-dialog-actions"><button type="button" className="button-secondary" disabled={busy} onClick={onClose}>Cancel</button><button type="submit" disabled={busy}>{busy ? <><RefreshCw size={16} className="spin" /> Saving</> : 'Save event'}</button></div></form>;
}

export default function Calendar() {
  const { user } = useAuth();
  const now = new Date();
  const [month, setMonth] = useState(() => new Date(now.getFullYear(), now.getMonth(), 1));
  const [items, setItems] = useState<CalendarItem[]>([]);
  const [selectedDate, setSelectedDate] = useState(() => dayKey(new Date()));
  const [selectedItem, setSelectedItem] = useState<CalendarItem | null>(null);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [dialogError, setDialogError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const canCreate = user?.role === 'ADMIN' || user?.role === 'MANAGER';
  const today = dayKey(new Date());
  const days = useMemo(() => {
    const first = new Date(month.getFullYear(), month.getMonth(), 1);
    const start = new Date(first);
    start.setDate(start.getDate() - start.getDay());
    const last = new Date(month.getFullYear(), month.getMonth() + 1, 0);
    const end = new Date(last);
    end.setDate(end.getDate() + 6 - end.getDay());
    return Array.from({ length: Math.round((end.getTime() - start.getTime()) / 86400000) + 1 }, (_, index) => new Date(start.getFullYear(), start.getMonth(), start.getDate() + index));
  }, [month]);
  const visibleStart = dayKey(days[0]);
  const visibleEnd = dayKey(days[days.length - 1]);

  const reload = () => setRefresh((value) => value + 1);
  useEffect(() => {
    setLoading(true);
    setError('');
    void calendar.feed(visibleStart, visibleEnd)
      .then(setItems)
      .catch(() => setError('Unable to load calendar events. Please try again.'))
      .finally(() => setLoading(false));
  }, [visibleStart, visibleEnd, refresh]);

  const selectedDayItems = useMemo(() => items.filter((item) => intersects(item, selectedDate)), [items, selectedDate]);
  const openDetail = (item: CalendarItem) => {
    setDialogError('');
    setSelectedItem(item);
    setDialog(null);
  };
  const closeOverlay = (force = false) => {
    if (busy && !force) return;
    setDialog(null);
    setSelectedItem(null);
    setDialogError('');
  };
  const submitEvent = async (value: EventFormValue) => {
    setBusy(true);
    setDialogError('');
    try {
      if (dialog === 'edit' && isEvent(selectedItem)) {
        await calendar.update(selectedItem.id, { title: value.title, description: value.description || null, event_type: value.eventType, start_at: value.start, end_at: value.end, all_day: value.allDay, location: value.location || null });
      } else {
        await calendar.create({ title: value.title, description: value.description || null, event_type: value.eventType, start_at: value.start, end_at: value.end, all_day: value.allDay, location: value.location || null });
      }
      closeOverlay(true);
      reload();
    } catch {
      setDialogError(dialog === 'edit' ? 'Unable to update this event.' : 'Unable to create this event.');
    } finally {
      setBusy(false);
    }
  };
  const removeEvent = async () => {
    if (!isEvent(selectedItem)) return;
    setBusy(true);
    setDialogError('');
    try {
      await calendar.delete(selectedItem.id);
      closeOverlay(true);
      reload();
    } catch {
      setDialogError('Unable to delete this event.');
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    if (!selectedItem && !dialog) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeOverlay();
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [selectedItem, dialog, busy]);

  return <main className="workspace-page calendar-workspace"><header className="page-header calendar-page-header"><div><p className="eyebrow">Workplace schedule</p><h1>Calendar</h1><p className="muted">Company events and approved leave visible to you.</p></div><div className="calendar-header-actions">{canCreate && <button type="button" onClick={() => { setSelectedItem(null); setDialogError(''); setDialog('create'); }}><Plus size={17} /> Create event</button>}<button type="button" className="button-secondary" disabled={loading} onClick={reload} aria-label="Refresh calendar"><RefreshCw size={16} className={loading ? 'spin' : ''} /></button></div></header>
    {error && <div className="calendar-error error" role="alert"><CircleAlert size={17} /><span>{error}</span><button type="button" className="button-secondary button-small" onClick={reload}>Try again</button></div>}
    <section className="calendar-layout"><section className="calendar-month-card" aria-label="Month calendar"><header className="calendar-toolbar"><div className="calendar-period-navigation"><button type="button" className="button-secondary calendar-icon-button" aria-label="Previous month" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))}><ChevronLeft size={18} /></button><h2>{month.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}</h2><button type="button" className="button-secondary calendar-icon-button" aria-label="Next month" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))}><ChevronRight size={18} /></button></div><button type="button" className="button-secondary button-small" onClick={() => { const current = new Date(); setMonth(new Date(current.getFullYear(), current.getMonth(), 1)); setSelectedDate(dayKey(current)); }}>Today</button></header><div className="calendar-weekdays">{weekdays.map((day) => <span key={day}>{day}</span>)}</div>{loading ? <CalendarLoading /> : <div className="calendar-month-grid">{days.map((day) => { const key = dayKey(day); const entries = items.filter((item) => intersects(item, key)); const outside = day.getMonth() !== month.getMonth(); return <button type="button" key={key} className={'calendar-day-cell ' + (outside ? 'outside' : '') + (key === today ? ' today' : '') + (key === selectedDate ? ' selected' : '')} onClick={() => setSelectedDate(key)} aria-pressed={key === selectedDate}><span className="calendar-day-number">{day.getDate()}</span><span className="calendar-day-items">{entries.slice(0, 3).map((item) => <EventPill key={item.kind + '-' + item.id} item={item} onSelect={() => openDetail(item)} />)}{entries.length > 3 && <span className="calendar-more-items">+{entries.length - 3} more</span>}</span></button>; })}</div>}</section>
      <aside className="calendar-agenda" aria-label="Selected day agenda"><header><div><p className="eyebrow">Selected day</p><h2>{dateOnly(selectedDate).toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}</h2></div><CalendarDays size={19} aria-hidden="true" /></header>{loading ? <div className="agenda-loading"><span /><span /></div> : selectedDayItems.length ? <div className="agenda-list">{selectedDayItems.map((item) => <button type="button" key={item.kind + '-' + item.id} className={'agenda-item ' + (item.kind === 'LEAVE' ? 'leave' : '')} onClick={() => openDetail(item)}><span>{item.kind === 'LEAVE' ? 'Approved leave' : itemTime(item)}</span><strong>{item.kind === 'LEAVE' ? 'Approved leave' : item.title}</strong><small>{item.kind === 'LEAVE' ? 'Leave projection · read only' : typeLabel(item.event_type)}</small></button>)}</div> : <div className="agenda-empty"><Clock3 size={22} /><p>No events for this day.</p><small>{canCreate ? 'Create an event or choose another day.' : 'Choose another day to view calendar activity.'}</small>{canCreate && <button type="button" className="button-secondary button-small" onClick={() => { setSelectedItem(null); setDialog('create'); }}>Create event</button>}</div>}</aside>
    </section>
    {!loading && !error && items.length === 0 && <p className="calendar-month-empty">No company events or approved leave appear in this view.</p>}
    {(selectedItem || dialog) && <div className="calendar-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeOverlay(); }}><section className="calendar-dialog" role="dialog" aria-modal="true" aria-labelledby="calendar-dialog-title"><header><div><p className="eyebrow">{dialog === 'create' ? 'New company event' : selectedItem?.kind === 'LEAVE' ? 'Approved leave' : dialog === 'edit' ? 'Edit event' : dialog === 'delete' ? 'Delete event' : 'Event details'}</p><h2 id="calendar-dialog-title">{dialog === 'create' ? 'Create event' : selectedItem?.kind === 'LEAVE' ? 'Approved leave' : selectedItem?.title}</h2></div><button type="button" className="calendar-dialog-close" aria-label="Close dialog" disabled={busy} onClick={() => closeOverlay()}><X size={18} /></button></header>{dialog === 'create' || dialog === 'edit' ? <CalendarForm key={(dialog === 'edit' ? selectedItem?.id : 'new') + '-' + selectedDate} item={dialog === 'edit' ? selectedItem ?? undefined : undefined} selectedDate={selectedDate} busy={busy} error={dialogError} onSubmit={(value) => void submitEvent(value)} onClose={closeOverlay} /> : dialog === 'delete' && isEvent(selectedItem) ? <div className="calendar-delete-confirm"><p>Delete <strong>{selectedItem.title}</strong>? This action cannot be undone.</p>{dialogError && <p className="error" role="alert">{dialogError}</p>}<div className="calendar-dialog-actions"><button type="button" className="button-secondary" disabled={busy} onClick={() => setDialog(null)}>Cancel</button><button type="button" className="calendar-delete-button" disabled={busy} onClick={() => void removeEvent()}>{busy ? <><RefreshCw size={16} className="spin" /> Deleting</> : <><Trash2 size={16} /> Delete event</>}</button></div></div> : selectedItem && <EventDetails item={selectedItem} canManage={canCreate} onEdit={() => setDialog('edit')} onDelete={() => setDialog('delete')} />}</section></div>}
  </main>;
}

function EventDetails({ item, canManage, onEdit, onDelete }: { item: CalendarItem; canManage: boolean; onEdit: () => void; onDelete: () => void }) {
  const leave = item.kind === 'LEAVE';
  return <div className="calendar-event-details">{leave ? <div className="leave-detail-notice"><CalendarDays size={18} /><p>This approved leave is shown from the authoritative leave request and cannot be edited here.</p></div> : <>{item.description ? <p className="calendar-detail-description">{item.description}</p> : <p className="calendar-detail-empty">No description provided.</p>}<dl><div><dt>When</dt><dd>{itemRange(item)}</dd></div><div><dt>Type</dt><dd>{typeLabel(item.event_type)}</dd></div>{item.location && <div><dt><MapPin size={14} /> Location</dt><dd>{item.location}</dd></div>}</dl>{canManage && <div className="calendar-detail-actions"><button type="button" className="button-secondary" onClick={onEdit}><Edit3 size={16} /> Edit</button><button type="button" className="calendar-delete-button" onClick={onDelete}><Trash2 size={16} /> Delete</button></div>}</>}</div>;
}

function CalendarLoading() {
  return <div className="calendar-loading" aria-label="Loading calendar"><span /><span /><span /><span /><span /><span /></div>;
}

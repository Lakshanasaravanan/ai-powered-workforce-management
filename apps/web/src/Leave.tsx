import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { CalendarDays, CheckCircle2, ChevronDown, ClipboardList, Clock3, Filter, Plus, RefreshCw, Send, UserRound, XCircle } from 'lucide-react';
import { ApiError, type HalfDayPeriod, type LeaveRequest, type LeaveStatus, type LeaveType, leaves } from './lib/api';
import { useAuth } from './auth';

type Props = { onNotificationChange: () => void };
type FilterStatus = 'ALL' | LeaveStatus;
type LeaveFormValue = { leaveType: LeaveType; startDate: string; endDate: string; period: HalfDayPeriod | ''; reason: string };

const leaveLabels: Record<LeaveType, string> = {
  CASUAL: 'Casual leave',
  MEDICAL: 'Medical leave',
  EMERGENCY: 'Emergency leave',
  DAY_OFF: 'Day off',
};

const leaveTypes: LeaveType[] = ['CASUAL', 'MEDICAL', 'EMERGENCY', 'DAY_OFF'];
const formatDate = (value: string) => new Date(value.slice(0, 10) + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
const formatShortDate = (value: string) => new Date(value.slice(0, 10) + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
const leaveRange = (leave: LeaveRequest) => leave.start_date === leave.end_date ? formatDate(leave.start_date) : formatShortDate(leave.start_date) + ' – ' + formatDate(leave.end_date);

function apiMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Unable to reach the EMS service. Please try again.';
  if (error.status === 403) return 'You are not authorized to perform that action.';
  if (error.status === 409) return 'This leave request has already changed. Latest data was loaded.';
  if (error.status === 422) return 'Please review the leave details and try again.';
  return 'Unable to complete the request. Please try again.';
}

function StatusBadge({ status }: { status: LeaveStatus }) {
  return <span className={'status status-' + status.toLowerCase()}>{status[0] + status.slice(1).toLowerCase()}</span>;
}

function SummaryCard({ status, count }: { status: LeaveStatus; count: number }) {
  const icon = status === 'PENDING' ? <Clock3 size={18} /> : status === 'APPROVED' ? <CheckCircle2 size={18} /> : <XCircle size={18} />;
  return <article className={'leave-summary-card ' + status.toLowerCase()}><span aria-hidden="true">{icon}</span><div><strong>{count}</strong><small>{status[0] + status.slice(1).toLowerCase()} request{count === 1 ? '' : 's'}</small></div></article>;
}

function LeaveRequestForm({ onSubmit, submitting, onCancel }: { onSubmit: (value: LeaveFormValue) => void; submitting: boolean; onCancel: () => void }) {
  const [leaveType, setLeaveType] = useState<LeaveType>('CASUAL');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [period, setPeriod] = useState<HalfDayPeriod | ''>('');
  const [reason, setReason] = useState('');
  const [validationError, setValidationError] = useState('');
  const dayOff = leaveType === 'DAY_OFF';

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const end = dayOff ? startDate : endDate;
    if (!startDate || !end || !reason.trim() || (dayOff && !period)) {
      setValidationError('Complete all required request details.');
      return;
    }
    if (end < startDate) {
      setValidationError('End date must be on or after the start date.');
      return;
    }
    setValidationError('');
    onSubmit({ leaveType, startDate, endDate: end, period, reason: reason.trim() });
  };

  return <section className="leave-request-card" aria-labelledby="request-leave-title"><div className="leave-request-header"><div><p className="eyebrow">New request</p><h2 id="request-leave-title">Request leave</h2><p>Submit dates and a brief reason. Status is determined by the existing leave workflow.</p></div><button type="button" className="button-secondary button-small" onClick={onCancel}><ChevronDown size={15} /> Close</button></div><form onSubmit={submit}><div className="leave-form-grid"><label htmlFor="leave-type">Leave type<select id="leave-type" value={leaveType} onChange={(event) => { setLeaveType(event.target.value as LeaveType); setPeriod(''); }} disabled={submitting}>{leaveTypes.map((type) => <option key={type} value={type}>{leaveLabels[type]}</option>)}</select></label><label htmlFor="leave-start">{dayOff ? 'Date' : 'Start date'}<input id="leave-start" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} disabled={submitting} required /></label>{!dayOff ? <label htmlFor="leave-end">End date<input id="leave-end" type="date" value={endDate} min={startDate || undefined} onChange={(event) => setEndDate(event.target.value)} disabled={submitting} required /></label> : <label htmlFor="half-day-period">Half-day period<select id="half-day-period" value={period} onChange={(event) => setPeriod(event.target.value as HalfDayPeriod)} disabled={submitting} required><option value="">Select period</option><option value="MORNING">Morning</option><option value="AFTERNOON">Afternoon</option></select></label>}<label className="leave-reason-field" htmlFor="leave-reason">Reason<textarea id="leave-reason" value={reason} maxLength={2000} onChange={(event) => setReason(event.target.value)} disabled={submitting} required placeholder="Briefly describe your request" /></label></div>{validationError && <p className="error" role="alert">{validationError}</p>}<div className="leave-form-actions"><small>All requests are reviewed according to the existing leave workflow.</small><button disabled={submitting} type="submit">{submitting ? <><RefreshCw size={16} className="spin" /> Submitting</> : <><Send size={16} /> Submit request</>}</button></div></form></section>;
}

function LeaveRow({ leave, team, busy, onApprove, onReject }: { leave: LeaveRequest; team?: boolean; busy?: boolean; onApprove?: () => void; onReject?: (note: string) => void }) {
  const [rejecting, setRejecting] = useState(false);
  const [note, setNote] = useState('');
  return <article className="leave-request-row"><div className="leave-request-main"><span className="leave-type-icon" aria-hidden="true"><CalendarDays size={17} /></span><div><div className="leave-row-heading"><strong>{team ? leave.employee.full_name : leaveLabels[leave.leave_type]}</strong><StatusBadge status={leave.status} /></div>{team && <small>{leave.employee.employee_code} · {leaveLabels[leave.leave_type]}</small>}<p>{leaveRange(leave)}{leave.duration === 'HALF_DAY' ? ' · ' + (leave.half_day_period === 'MORNING' ? 'Morning half-day' : 'Afternoon half-day') : ''}</p><small>Requested {new Date(leave.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</small></div></div><div className="leave-request-details"><p>{leave.reason}</p>{leave.decision_note && <small className="decision-note">Decision note: {leave.decision_note}</small>}{leave.decision_source === 'AUTOMATIC_POLICY' && <small className="automatic-note">Automatically approved by the existing workflow.</small>}{team && leave.status === 'PENDING' && leave.approval_required && onApprove && onReject && <div className="manager-decision">{rejecting ? <><label htmlFor={'reject-note-' + leave.id}>Rejection note <span>(optional)</span><textarea id={'reject-note-' + leave.id} value={note} onChange={(event) => setNote(event.target.value)} disabled={busy} placeholder="Add a note for the employee" /></label><div><button type="button" className="button-secondary button-small" disabled={busy} onClick={() => { setRejecting(false); setNote(''); }}>Cancel</button><button type="button" className="reject-button button-small" disabled={busy} onClick={() => onReject(note)}>Confirm rejection</button></div></> : <div><button type="button" className="button-small" disabled={busy} onClick={onApprove}>{busy ? 'Updating…' : 'Approve'}</button><button type="button" className="button-secondary button-small" disabled={busy} onClick={() => setRejecting(true)}>Reject</button></div>}</div>}</div></article>;
}

export default function Leave({ onNotificationChange }: Props) {
  const { user } = useAuth();
  const [mine, setMine] = useState<LeaveRequest[]>([]);
  const [team, setTeam] = useState<LeaveRequest[]>([]);
  const [view, setView] = useState<'mine' | 'team'>('mine');
  const [filter, setFilter] = useState<FilterStatus>('ALL');
  const [requestOpen, setRequestOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [decisionBusy, setDecisionBusy] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const ownRequests = await leaves.mine();
      setMine(ownRequests);
      if (user?.role === 'MANAGER') setTeam(await leaves.team());
      else setTeam([]);
    } catch (caught) {
      setError(apiMessage(caught));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [user?.role]);

  const submitRequest = async (value: LeaveFormValue) => {
    setSubmitting(true);
    setError('');
    try {
      const created = await leaves.create({ leave_type: value.leaveType, start_date: value.startDate, end_date: value.endDate, duration: value.leaveType === 'DAY_OFF' ? 'HALF_DAY' : 'FULL_DAY', ...(value.leaveType === 'DAY_OFF' ? { half_day_period: value.period as HalfDayPeriod } : {}), reason: value.reason });
      setFeedback(created.status === 'APPROVED' ? 'Your leave request was recorded as approved.' : 'Your leave request was submitted.');
      setRequestOpen(false);
      await load();
      onNotificationChange();
    } catch (caught) {
      setError(apiMessage(caught));
    } finally {
      setSubmitting(false);
    }
  };

  const decide = async (leave: LeaveRequest, action: 'approve' | 'reject', note?: string) => {
    setDecisionBusy(leave.id);
    setError('');
    try {
      if (action === 'approve') await leaves.approve(leave.id);
      else await leaves.reject(leave.id, note);
      setFeedback('Leave request ' + (action === 'approve' ? 'approved.' : 'rejected.'));
      await load();
      onNotificationChange();
    } catch (caught) {
      setError(apiMessage(caught));
      await load();
    } finally {
      setDecisionBusy(null);
    }
  };

  const visibleMine = useMemo(() => filter === 'ALL' ? mine : mine.filter((leave) => leave.status === filter), [filter, mine]);
  const currentItems = view === 'team' ? team : visibleMine;
  const counts = useMemo(() => ({ PENDING: mine.filter((item) => item.status === 'PENDING').length, APPROVED: mine.filter((item) => item.status === 'APPROVED').length, REJECTED: mine.filter((item) => item.status === 'REJECTED').length }), [mine]);

  return <main className="workspace-page leave-workspace"><header className="page-header leave-page-header"><div><p className="eyebrow">Time away</p><h1>Leave</h1><p className="muted">Request, track, and manage authorized leave activity.</p></div><div><button type="button" onClick={() => { setRequestOpen((open) => !open); setFeedback(''); }}><Plus size={17} /> {requestOpen ? 'Close request' : 'Request leave'}</button><button type="button" className="button-secondary" aria-label="Refresh leave requests" disabled={loading} onClick={() => void load()}><RefreshCw size={16} className={loading ? 'spin' : ''} /> Refresh</button></div></header>
    {error && <p className="error" role="alert">{error}</p>}{feedback && <p className="success" role="status">{feedback}</p>}
    <section className="leave-summary-grid" aria-label="Your leave request summary"><SummaryCard status="PENDING" count={counts.PENDING} /><SummaryCard status="APPROVED" count={counts.APPROVED} /><SummaryCard status="REJECTED" count={counts.REJECTED} /></section>
    {requestOpen && <LeaveRequestForm onSubmit={(value) => void submitRequest(value)} submitting={submitting} onCancel={() => setRequestOpen(false)} />}
    <section className="leave-history-card"><header className="leave-history-header"><div><p className="eyebrow">{view === 'team' ? 'Manager view' : 'Your requests'}</p><h2>{view === 'team' ? 'Direct-report leave' : 'Request history'}</h2></div><div className="leave-history-controls"><div className="leave-tabs" role="tablist" aria-label="Leave request scope"><button type="button" role="tab" aria-selected={view === 'mine'} className={view === 'mine' ? 'active-tab' : 'button-secondary'} onClick={() => setView('mine')}>My leave</button>{user?.role === 'MANAGER' && <button type="button" role="tab" aria-selected={view === 'team'} className={view === 'team' ? 'active-tab' : 'button-secondary'} onClick={() => setView('team')}>Team requests</button>}</div>{view === 'mine' && <label className="leave-filter"><Filter size={15} aria-hidden="true" /><span className="sr-only">Filter leave requests</span><select value={filter} onChange={(event) => setFilter(event.target.value as FilterStatus)}><option value="ALL">All statuses</option><option value="PENDING">Pending</option><option value="APPROVED">Approved</option><option value="REJECTED">Rejected</option></select></label>}</div></header>
      {loading ? <LeaveLoading /> : currentItems.length ? <div className="leave-request-list">{currentItems.map((leave) => <LeaveRow key={leave.id} leave={leave} team={view === 'team'} busy={decisionBusy === leave.id} onApprove={view === 'team' ? () => void decide(leave, 'approve') : undefined} onReject={view === 'team' ? (note) => void decide(leave, 'reject', note) : undefined} />)}</div> : <div className="leave-empty-state"><ClipboardList size={25} aria-hidden="true" /><h3>{view === 'team' ? 'No direct-report requests' : filter === 'ALL' ? 'No leave requests yet' : 'No matching requests'}</h3><p>{view === 'team' ? 'Requests from your direct reports will appear here when available.' : filter === 'ALL' ? 'When you submit a request, it will appear here with its current status.' : 'Try a different status filter to view other requests.'}</p>{view === 'mine' && filter === 'ALL' && <button type="button" className="button-secondary" onClick={() => setRequestOpen(true)}><Plus size={16} /> Request leave</button>}</div>}
    </section>
  </main>;
}

function LeaveLoading() {
  return <div className="leave-loading" aria-label="Loading leave requests"><span /><span /><span /></div>;
}

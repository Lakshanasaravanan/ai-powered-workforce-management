const base = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8001';
const agentBase = import.meta.env.VITE_AGENT_API_BASE_URL ?? 'http://localhost:8000';

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) { super(message); }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(base + path, { ...init, headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${sessionStorage.getItem('infotech_token') ?? ''}`, ...init.headers } });
  if (!response.ok) {
    if (response.status === 401) { sessionStorage.removeItem('infotech_token'); window.dispatchEvent(new Event('infotech:unauthorized')); }
    let message = 'The request could not be completed.';
    try { const payload = await response.json(); if (typeof payload.detail === 'string') message = payload.detail; } catch { /* Keep server internals private. */ }
    throw new ApiError(response.status, message);
  }
  return response.json() as Promise<T>;
}

export type Employee = { id: string; employee_code: string; full_name: string; company_email: string; role: string; designation: string; department: string; manager_id: string | null; is_active: boolean; archived_at?: string | null; };
export type CompensationConfiguration = { id: string; monthly_salary: string; overtime_hourly_rate: string; late_deduction_amount: string; effective_from: string; effective_to: string | null; };
export type LeaveType = 'CASUAL' | 'MEDICAL' | 'EMERGENCY' | 'DAY_OFF';
export type LeaveStatus = 'PENDING' | 'APPROVED' | 'REJECTED';
export type LeaveDuration = 'FULL_DAY' | 'HALF_DAY';
export type HalfDayPeriod = 'MORNING' | 'AFTERNOON';
export type DecisionSource = 'AUTOMATIC_POLICY' | 'MANAGER';
export type LeaveRequest = { id: string; employee: Pick<Employee, 'id' | 'employee_code' | 'full_name'>; leave_type: LeaveType; status: LeaveStatus; start_date: string; end_date: string; duration: LeaveDuration; half_day_period: HalfDayPeriod | null; reason: string; approval_required: boolean; decided_by_id: string | null; decided_at: string | null; decision_note: string | null; decision_source: DecisionSource | null; manager_notification_delivered: boolean | null; created_at: string; updated_at: string; };
export type NotificationCategory = 'LEAVE' | 'CHAT' | 'CALENDAR' | 'SYSTEM';
export type Notification = { id: string; category: NotificationCategory; title: string; message: string; is_read: boolean; read_at: string | null; related_entity_type: string | null; related_entity_id: string | null; created_at: string; };
export type ChatMessage = { id: string; conversation_id: string; sender_employee_id: string; content: string; created_at: string; };
export type ChatConversation = { id: string; type: 'DIRECT' | 'GROUP'; name: string | null; created_by: string; updated_at: string; unread_count: number; last_message: ChatMessage | null; };
export type PolicyCitation = { document: string; page: number; section: string | null; subsection: string | null };
export type AgentAction = { action_id: string; tool_name: 'apply_leave' | 'approve_leave' | 'reject_leave'; safe_display: Record<string, string | null>; created_at: string; expires_at: string; state: string };
export type PolicyAnswer = { answer: string; sources: PolicyCitation[]; conversation_id: string; request_id: string | null; response_type?: 'message' | 'clarification' | 'action_proposal'; action?: AgentAction | null };
export type ActionResult = { action_id: string; state: string; message: string; conversation_id: string; request_id: string | null };

function agentErrorMessage(status: number): string {
  if (status === 401) return 'Your session has expired. Please sign in again.';
  if (status === 403) return 'You are not authorized to use InfoTech Agent.';
  if (status === 422) return 'InfoTech Agent could not safely process that request.';
  if (status === 429) return 'Too many requests. Please try again shortly.';
  if (status === 503) return 'InfoTech Agent is temporarily unavailable. Please try again later.';
  return 'InfoTech Agent could not complete this request.';
}

function isPolicyAnswer(value: unknown): value is PolicyAnswer {
  if (!value || typeof value !== 'object') return false;
  const response = value as Record<string, unknown>;
  return typeof response.answer === 'string'
    && typeof response.conversation_id === 'string'
    && (response.request_id === null || typeof response.request_id === 'string')
    && Array.isArray(response.sources)
    && response.sources.every((source) => {
      if (!source || typeof source !== 'object') return false;
      const citation = source as Record<string, unknown>;
      return typeof citation.document === 'string'
        && typeof citation.page === 'number'
        && (citation.section === null || typeof citation.section === 'string')
        && (citation.subsection === null || typeof citation.subsection === 'string');
    });
}

export const employees = {
  list: () => request<Employee[]>('/api/v1/employees'),
  search: (query: string) => request<Employee[]>(`/api/v1/employees/search?q=${encodeURIComponent(query)}`),
  create: (body: object) => request<Employee & { temporary_password: string }>('/api/v1/employees', { method: 'POST', body: JSON.stringify(body) }),
  update: (id: string, body: object) => request<Employee>(`/api/v1/employees/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  archive: (id: string) => request<{ ok: boolean }>(`/api/v1/employees/${id}`, { method: 'DELETE' }),
  compensation: (id: string) => request<CompensationConfiguration[]>(`/api/v1/employees/${id}/compensation`),
  setCompensation: (id: string, body: { monthly_salary: string; overtime_hourly_rate: string; late_deduction_amount: string; effective_from: string }) => request<CompensationConfiguration>(`/api/v1/employees/${id}/compensation`, { method: 'POST', body: JSON.stringify(body) }),
};
export const leaves = {
  mine: () => request<LeaveRequest[]>('/api/v1/leaves/me'), team: () => request<LeaveRequest[]>('/api/v1/leaves/team'),
  create: (body: { leave_type: LeaveType; start_date: string; end_date: string; duration: LeaveDuration; half_day_period?: HalfDayPeriod; reason: string; }) => request<LeaveRequest>('/api/v1/leaves', { method: 'POST', body: JSON.stringify(body) }),
  approve: (id: string) => request<LeaveRequest>(`/api/v1/leaves/${id}/approve`, { method: 'POST', body: JSON.stringify({}) }),
  reject: (id: string, decision_note?: string) => request<LeaveRequest>(`/api/v1/leaves/${id}/reject`, { method: 'POST', body: JSON.stringify({ decision_note }) }),
};
export const notifications = {
  list: () => request<Notification[]>('/api/v1/notifications'), unreadCount: () => request<{ unread_count: number }>('/api/v1/notifications/unread-count'),
  markRead: (id: string) => request<Notification>(`/api/v1/notifications/${id}/read`, { method: 'POST' }),
  markAllRead: () => request<{ updated_count: number }>('/api/v1/notifications/read-all', { method: 'POST' }),
};
export const chat = {
  websocketTicket: () => request<{ ticket: string; expires_in: number }>('/api/v1/chat/ws-ticket', { method: 'POST' }),
  conversations: () => request<ChatConversation[]>('/api/v1/chat/conversations'),
  direct: (target_employee_id: string) => request<ChatConversation>('/api/v1/chat/conversations/direct', { method: 'POST', body: JSON.stringify({ target_employee_id }) }),
  group: (name: string, participant_employee_ids: string[]) => request<ChatConversation>('/api/v1/chat/conversations/group', { method: 'POST', body: JSON.stringify({ name, participant_employee_ids }) }),
  messages: (id: string) => request<ChatMessage[]>(`/api/v1/chat/conversations/${id}/messages`),
  send: (id: string, content: string) => request<ChatMessage>(`/api/v1/chat/conversations/${id}/messages`, { method: 'POST', body: JSON.stringify({ content }) }),
  read: (id: string) => request<{ ok: boolean }>(`/api/v1/chat/conversations/${id}/read`, { method: 'POST' }),
};
export type CalendarItem={id:string;title:string;event_type:string;start_at:string;end_at:string;all_day:boolean;kind:string;description?:string|null;location?:string|null};
export const calendar={feed:(start:string,end:string)=>request<CalendarItem[]>(`/api/v1/calendar/feed?start=${start}&end=${end}`),get:(id:string)=>request<CalendarItem>(`/api/v1/calendar/events/${id}`),create:(body:object)=>request<CalendarItem>('/api/v1/calendar/events',{method:'POST',body:JSON.stringify(body)}),update:(id:string,body:object)=>request<CalendarItem>(`/api/v1/calendar/events/${id}`,{method:'PATCH',body:JSON.stringify(body)}),delete:(id:string)=>request<{ok:boolean}>(`/api/v1/calendar/events/${id}`,{method:'DELETE'})};

export const policyAssistant = {
  async query(message: string, conversationId?: string): Promise<PolicyAnswer> {
    let response: Response;
    try {
      response = await fetch(`${agentBase}/api/v1/agent/query`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${sessionStorage.getItem('infotech_token') ?? ''}`,
        },
        body: JSON.stringify({ message, ...(conversationId ? { conversation_id: conversationId } : {}) }),
      });
    } catch {
      throw new ApiError(0, 'Unable to reach InfoTech Agent. Please check your connection and try again.');
    }
    if (!response.ok) {
      if (response.status === 401) {
        sessionStorage.removeItem('infotech_token');
        window.dispatchEvent(new Event('infotech:unauthorized'));
      }
      throw new ApiError(response.status, agentErrorMessage(response.status));
    }
    let payload: unknown;
    try { payload = await response.json(); } catch { throw new ApiError(502, 'The policy assistant returned an unexpected response.'); }
    if (!isPolicyAnswer(payload)) throw new ApiError(502, 'The policy assistant returned an unexpected response.');
    return payload;
  },
  async action(actionId: string, conversationId: string, operation: 'confirm' | 'cancel'): Promise<ActionResult> {
    const response = await fetch(`${agentBase}/api/v1/agent/actions/${encodeURIComponent(actionId)}/${operation}`, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${sessionStorage.getItem('infotech_token') ?? ''}` }, body: JSON.stringify({ conversation_id: conversationId }) });
    if (!response.ok) throw new ApiError(response.status, agentErrorMessage(response.status));
    return response.json() as Promise<ActionResult>;
  },
};

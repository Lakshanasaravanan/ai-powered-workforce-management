import { useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { BookOpen, Bot, CheckCircle2, ChevronRight, CircleAlert, ClipboardCheck, LoaderCircle, Send, ShieldCheck, Sparkles, X } from 'lucide-react';
import { ApiError, type AgentAction, type PolicyCitation, policyAssistant } from './lib/api';

type AgentMessage = { id: string; role: 'employee' | 'assistant'; content: string; sources?: PolicyCitation[]; action?: AgentAction; result?: string };

const suggestions = [
  'What is the company’s leave policy?',
  'Who is my manager?',
  'Apply for casual leave tomorrow.',
];

function sourceLabel(source: PolicyCitation): string {
  const location = [source.section, source.subsection].filter(Boolean).join(' — ');
  return source.document + ', page ' + source.page + (location ? ' · ' + location : '');
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : 'Unable to reach the workplace assistant. Please check your connection and try again.';
}

function ActionCard({ action, pending, onConfirm, onCancel }: { action: AgentAction; pending: boolean; onConfirm: () => void; onCancel: () => void }) {
  const fields = Object.entries(action.safe_display).filter(([key, value]) => key !== 'title' && value);
  return <section className="agent-action-card" aria-label="Action confirmation"><header><span><ClipboardCheck size={18} aria-hidden="true" /></span><div><p>Confirmation required</p><h3>{action.safe_display.title ?? 'Review action'}</h3></div></header>{fields.length > 0 && <dl>{fields.map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{value}</dd></div>)}</dl>}<p className="agent-action-note"><ShieldCheck size={14} aria-hidden="true" /> Nothing happens until you confirm.</p><div className="agent-action-buttons"><button type="button" disabled={pending} onClick={onConfirm}>{pending ? <><LoaderCircle size={16} className="spin" /> Confirming</> : 'Confirm action'}</button><button type="button" className="button-secondary" disabled={pending} onClick={onCancel}>Cancel</button></div></section>;
}

function CitationList({ sources }: { sources: PolicyCitation[] }) {
  return <details className="agent-citations"><summary><BookOpen size={14} aria-hidden="true" /> Policy sources ({sources.length})</summary><ul>{sources.map((source, index) => <li key={source.document + '-' + source.page + '-' + index}>{sourceLabel(source)}</li>)}</ul></details>;
}

export default function Agent() {
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [conversationId, setConversationId] = useState<string>();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();
  const [retryMessage, setRetryMessage] = useState<string>();
  const [actionPending, setActionPending] = useState<string>();
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const ask = async (rawMessage: string) => {
    const message = rawMessage.trim();
    if (!message || pending) return;
    setPending(true);
    setError(undefined);
    setRetryMessage(undefined);
    setDraft('');
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'employee', content: message }]);
    try {
      const response = await policyAssistant.query(message, conversationId);
      setConversationId(response.conversation_id);
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'assistant', content: response.answer, sources: response.sources, action: response.action ?? undefined }]);
    } catch (caught) {
      setError(errorMessage(caught));
      setRetryMessage(message);
    } finally {
      setPending(false);
    }
  };

  const executeAction = async (messageId: string, action: AgentAction, operation: 'confirm' | 'cancel') => {
    if (!conversationId || actionPending) return;
    setActionPending(action.action_id);
    setError(undefined);
    try {
      const result = await policyAssistant.action(action.action_id, conversationId, operation);
      setMessages((items) => items.map((item) => item.id === messageId ? { ...item, action: undefined, result: result.message } : item));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setActionPending(undefined);
    }
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void ask(draft);
  };
  const keyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void ask(draft);
    }
  };
  const useSuggestion = (suggestion: string) => {
    setDraft(suggestion);
    inputRef.current?.focus();
  };

  return <main className="workspace-page agent-workspace">
    <header className="page-header agent-page-header"><div><p className="eyebrow">Authenticated workplace assistant</p><h1>InfoTech Agent</h1><p className="muted">Ask grounded policy questions, retrieve your workforce information, or review a prepared action.</p></div><div className="agent-header-mark" aria-label="InfoTech Agent"><Bot size={21} aria-hidden="true" /></div></header>
    <section className="agent-panel" aria-label="InfoTech Agent conversation">
      <div className="agent-conversation" aria-live="polite">{messages.length === 0 ? <div className="agent-welcome"><span className="agent-welcome-icon"><Sparkles size={25} /></span><h2>How can I help?</h2><p>I can answer company-policy questions, look up your manager, or prepare an available workforce action for your review.</p><div className="agent-suggestions" aria-label="Example prompts">{suggestions.map((suggestion) => <button key={suggestion} type="button" className="button-secondary" onClick={() => useSuggestion(suggestion)}>{suggestion}<ChevronRight size={15} aria-hidden="true" /></button>)}</div></div> : <div className="agent-message-list">{messages.map((message) => <article key={message.id} className={'agent-message ' + message.role}><header><span className="agent-message-avatar" aria-hidden="true">{message.role === 'employee' ? 'You' : <Bot size={15} />}</span><strong>{message.role === 'employee' ? 'You' : 'InfoTech Agent'}</strong></header><div className="agent-message-content"><p>{message.content}</p>{message.action && <ActionCard action={message.action} pending={actionPending === message.action.action_id} onConfirm={() => void executeAction(message.id, message.action!, 'confirm')} onCancel={() => void executeAction(message.id, message.action!, 'cancel')} />}{message.result && <div className="agent-action-result"><CheckCircle2 size={16} aria-hidden="true" /><span>{message.result}</span></div>}{message.role === 'assistant' && message.sources && message.sources.length > 0 && <CitationList sources={message.sources} />}</div></article>)}{pending && <article className="agent-message assistant agent-thinking"><header><span className="agent-message-avatar" aria-hidden="true"><Bot size={15} /></span><strong>InfoTech Agent</strong></header><div className="agent-thinking-content"><LoaderCircle size={17} className="spin" /><span>Preparing a response…</span></div></article>}</div>}</div>
      {error && <div className="agent-error error" role="alert"><CircleAlert size={17} aria-hidden="true" /><span>{error}</span>{retryMessage && <button type="button" className="button-secondary button-small" onClick={() => void ask(retryMessage)} disabled={pending}>Try again</button>}<button type="button" className="agent-error-dismiss" aria-label="Dismiss error" onClick={() => setError(undefined)}><X size={16} /></button></div>}
      <form className="agent-composer" onSubmit={submit}><label htmlFor="policy-question">Ask InfoTech Agent</label><textarea id="policy-question" ref={inputRef} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={keyDown} placeholder="Ask about a policy or your workplace…" rows={3} disabled={pending} /><div><small>Enter to send · Shift + Enter for a new line</small><button type="submit" disabled={pending || !draft.trim()}>{pending ? <><LoaderCircle size={16} className="spin" /> Thinking</> : <><Send size={16} /> Send</>}</button></div></form>
    </section>
  </main>;
}

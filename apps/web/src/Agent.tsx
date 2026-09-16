import { FormEvent, KeyboardEvent, useState } from 'react';
import { ApiError, AgentAction, PolicyCitation, policyAssistant } from './lib/api';

type ChatMessage = { id: string; role: 'employee' | 'assistant'; content: string; sources?: PolicyCitation[]; action?: AgentAction; result?: string };

function sourceLabel(source: PolicyCitation): string {
  const location = [source.section, source.subsection].filter(Boolean).join(' — ');
  return `${source.document}, page ${source.page}${location ? ` · ${location}` : ''}`;
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : 'Unable to reach the policy assistant. Please check your connection and try again.';
}

export default function Agent() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [conversationId, setConversationId] = useState<string>();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();
  const [retryMessage, setRetryMessage] = useState<string>();
  const [actionPending, setActionPending] = useState<string>();

  const ask = async (rawMessage: string) => {
    const message = rawMessage.trim();
    if (!message || pending) return;
    setPending(true); setError(undefined); setRetryMessage(undefined); setDraft('');
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'employee', content: message }]);
    try {
      const response = await policyAssistant.query(message, conversationId);
      setConversationId(response.conversation_id);
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'assistant', content: response.answer, sources: response.sources, action: response.action ?? undefined }]);
    } catch (caught) {
      setError(errorMessage(caught)); setRetryMessage(message);
    } finally { setPending(false); }
  };
  const executeAction = async (messageId: string, action: AgentAction, operation: 'confirm' | 'cancel') => {
    if (!conversationId || actionPending) return;
    setActionPending(action.action_id); setError(undefined);
    try { const result = await policyAssistant.action(action.action_id, conversationId, operation); setMessages((items) => items.map((item) => item.id === messageId ? { ...item, action: undefined, result: result.message } : item)); }
    catch (caught) { setError(errorMessage(caught)); } finally { setActionPending(undefined); }
  };

  const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); void ask(draft); };
  const keyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void ask(draft); }
  };

  return <main className="workspace-page policy-assistant">
    <header><div><p className="eyebrow">InfoTech Workspace</p><h1>InfoTech Company Policy Assistant</h1><p className="muted">Ask policy questions, review workforce information, or confirm a server-prepared action.</p></div></header>
    <section className="assistant-card" aria-live="polite">
      {messages.length === 0 ? <div className="assistant-welcome"><h2>How can I help with company policy?</h2><p className="muted">For example: “What is the leave policy?” or “What guidance applies to attendance?”</p></div> :
        <div className="conversation" aria-label="Policy assistant conversation">{messages.map((message) => <article key={message.id} className={`chat-message ${message.role}`}><p className="chat-role">{message.role === 'employee' ? 'You' : 'Policy Assistant'}</p><p>{message.content}</p>{message.result && <p className="action-result">{message.result}</p>}{message.action && <div className="action-card"><strong>{message.action.safe_display.title ?? 'Review action'}</strong>{Object.entries(message.action.safe_display).filter(([key, value]) => key !== 'title' && value).map(([key, value]) => <p key={key}><span>{key.replaceAll('_', ' ')}:</span> {value}</p>)}<div><button type="button" disabled={!!actionPending} onClick={() => void executeAction(message.id, message.action!, 'confirm')}>{actionPending === message.action.action_id ? 'Confirming…' : 'Confirm'}</button><button type="button" className="ghost" disabled={!!actionPending} onClick={() => void executeAction(message.id, message.action!, 'cancel')}>Cancel</button></div></div>}{message.role === 'assistant' && message.sources && message.sources.length > 0 && <div className="citations" aria-label="Sources"><strong>Sources</strong><ul>{message.sources.map((source, index) => <li key={`${source.document}-${source.page}-${index}`}>{sourceLabel(source)}</li>)}</ul></div>}</article>)}{pending && <article className="chat-message assistant pending"><p className="chat-role">Policy Assistant</p><p>Finding relevant policy information…</p></article>}</div>}
      {error && <div className="assistant-error error" role="alert"><p>{error}</p>{retryMessage && <button type="button" className="ghost" onClick={() => void ask(retryMessage)} disabled={pending}>Try again</button>}</div>}
      <form className="assistant-composer" onSubmit={submit}><label htmlFor="policy-question">Your policy question</label><textarea id="policy-question" value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={keyDown} placeholder="Ask about a company policy…" rows={4} disabled={pending} /><div className="composer-actions"><small>Press Enter to send; Shift+Enter for a new line.</small><button type="submit" disabled={pending || !draft.trim()}>{pending ? 'Sending…' : 'Send question'}</button></div></form>
    </section>
  </main>;
}

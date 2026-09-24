import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { ChevronLeft, CircleAlert, LoaderCircle, MessageCircle, Plus, Search, Send, UserRound, Users, Wifi, WifiOff, X } from 'lucide-react';
import { ApiError, chat, ChatConversation, ChatMessage, employees, Employee } from './lib/api';
import { useAuth } from './auth';

type ConnectionState = 'connecting' | 'connected' | 'reconnecting' | 'disconnected';
type MessageGroup = { senderId: string; messages: ChatMessage[] };

function initials(name: string): string {
  return name.split(' ').filter(Boolean).map((part) => part[0]).join('').slice(0, 2).toUpperCase() || 'IT';
}

function conversationTitle(conversation: ChatConversation): string {
  return conversation.type === 'GROUP' ? conversation.name || 'Group conversation' : 'Direct conversation';
}

function formatTimestamp(value: string): string {
  const timestamp = new Date(value);
  const today = new Date();
  return timestamp.toLocaleString(undefined, timestamp.toDateString() === today.toDateString()
    ? { hour: 'numeric', minute: '2-digit' }
    : { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

function groupMessages(items: ChatMessage[]): MessageGroup[] {
  return items.reduce<MessageGroup[]>((groups, message) => {
    const current = groups.at(-1);
    const previousAt = current?.messages.at(-1)?.created_at;
    const closeInTime = previousAt && Math.abs(new Date(message.created_at).getTime() - new Date(previousAt).getTime()) < 5 * 60 * 1000;
    if (current && current.senderId === message.sender_employee_id && closeInTime) current.messages.push(message);
    else groups.push({ senderId: message.sender_employee_id, messages: [message] });
    return groups;
  }, []);
}

function ConversationAvatar({ conversation, label }: { conversation: ChatConversation; label?: string }) {
  return <span className={'conversation-avatar ' + (conversation.type === 'GROUP' ? 'group' : '')} aria-hidden="true">{conversation.type === 'GROUP' ? <Users size={16} /> : label ? initials(label) : <UserRound size={16} />}</span>;
}

function ConnectionIndicator({ state }: { state: ConnectionState }) {
  const content = state === 'connected'
    ? { label: 'Realtime connected', icon: <Wifi size={13} /> }
    : state === 'connecting'
      ? { label: 'Connecting to realtime updates', icon: <LoaderCircle size={13} className="spin" /> }
      : state === 'reconnecting'
        ? { label: 'Reconnecting to realtime updates', icon: <LoaderCircle size={13} className="spin" /> }
        : { label: 'Realtime updates unavailable', icon: <WifiOff size={13} /> };
  const shortLabel = state === 'connected' ? 'Live' : state === 'reconnecting' ? 'Reconnecting' : state === 'connecting' ? 'Connecting' : 'Offline';
  return <span className={'connection-state ' + state} title={content.label}>{content.icon}<span>{shortLabel}</span></span>;
}

function ConversationListLoading() {
  return <div className="conversation-loading" aria-label="Loading conversations"><span /><span /><span /><span /></div>;
}

function MessageLoading() {
  return <div className="message-loading" aria-label="Loading message history"><span /><span /><span /></div>;
}

function MessageGroupView({ group, mine }: { group: MessageGroup; mine: boolean }) {
  return <article className={'message-group ' + (mine ? 'mine' : 'theirs')}><div className="message-bubbles">{group.messages.map((message, index) => <div className="message-bubble" key={message.id}><p>{message.content}</p>{index === group.messages.length - 1 && <time dateTime={message.created_at}>{formatTimestamp(message.created_at)}</time>}</div>)}</div></article>;
}

export default function Chat() {
  const { user } = useAuth();
  const [conversations, setConversations] = useState<ChatConversation[]>([]);
  const [selected, setSelected] = useState<ChatConversation | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [people, setPeople] = useState<Employee[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [composer, setComposer] = useState('');
  const [newMessageOpen, setNewMessageOpen] = useState(false);
  const [conversationsLoading, setConversationsLoading] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [historyError, setHistoryError] = useState('');
  const [connectionState, setConnectionState] = useState<ConnectionState>('connecting');
  const messageRegion = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const selectedConversationId = useRef<string | null>(null);

  const loadConversations = async () => {
    setConversationsLoading(true);
    try {
      setConversations(await chat.conversations());
    } catch (caught) {
      setError(errorMessage(caught, 'Chat is unavailable. Please try again.'));
    } finally {
      setConversationsLoading(false);
    }
  };

  const loadMessages = async (conversation: ChatConversation) => {
    setHistoryLoading(true);
    setHistoryError('');
    stickToBottom.current = true;
    try {
      const history = await chat.messages(conversation.id);
      setMessages(history.sort((a, b) => a.created_at.localeCompare(b.created_at)));
      await chat.read(conversation.id);
      void loadConversations();
    } catch (caught) {
      setHistoryError(errorMessage(caught, 'Unable to load this conversation.'));
      setMessages([]);
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => { void loadConversations(); }, []);
  useEffect(() => { if (selected) void loadMessages(selected); else setMessages([]); }, [selected?.id]);
  useEffect(() => { selectedConversationId.current = selected?.id ?? null; }, [selected?.id]);

  useEffect(() => {
    if (searchQuery.trim().length < 2) {
      setPeople([]);
      setSearchLoading(false);
      return;
    }
    let active = true;
    const timer = window.setTimeout(() => {
      setSearchLoading(true);
      void employees.search(searchQuery.trim())
        .then((results) => { if (active) setPeople(results.filter((person) => person.id !== user?.id)); })
        .catch(() => { if (active) setPeople([]); })
        .finally(() => { if (active) setSearchLoading(false); });
    }, 220);
    return () => { active = false; window.clearTimeout(timer); };
  }, [searchQuery, user?.id]);

  useEffect(() => {
    let socket: WebSocket | undefined;
    let retry: number | undefined;
    let stopped = false;
    const base = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8001').replace(/^http/, 'ws');
    const reconnect = () => {
      if (!stopped) {
        setConnectionState('reconnecting');
        retry = window.setTimeout(() => void connect(), 2000);
      }
    };
    const connect = async () => {
      setConnectionState(socket ? 'reconnecting' : 'connecting');
      try {
        const ticketResponse = await chat.websocketTicket();
        if (stopped) return;
        socket = new WebSocket(base + '/api/v1/chat/ws', ['infotech.chat.ticket.' + ticketResponse.ticket]);
        socket.onopen = () => setConnectionState('connected');
        socket.onmessage = (event) => {
          try {
            const value = JSON.parse(event.data);
            if (value?.type !== 'message.created' || !value.message || typeof value.message.id !== 'string') return;
            if (value.message.conversation_id === selectedConversationId.current) {
              setMessages((current) => current.some((message) => message.id === value.message.id) ? current : [...current, value.message].sort((a, b) => a.created_at.localeCompare(b.created_at)));
            }
            void loadConversations();
          } catch {
            // Ignore malformed server events rather than exposing their payload.
          }
        };
        socket.onclose = (event) => {
          if (event.code === 1008) {
            setConnectionState('disconnected');
            return;
          }
          reconnect();
        };
        socket.onerror = () => setConnectionState('disconnected');
      } catch (caught) {
        if (caught instanceof ApiError && caught.status === 401) {
          setConnectionState('disconnected');
          return;
        }
        reconnect();
      }
    };
    void connect();
    return () => {
      stopped = true;
      if (retry !== undefined) window.clearTimeout(retry);
      socket?.close();
    };
  }, []);

  useEffect(() => {
    if (!stickToBottom.current || !messageRegion.current) return;
    messageRegion.current.scrollTop = messageRegion.current.scrollHeight;
  }, [messages, historyLoading, selected?.id]);

  const startDirect = async (employee: Employee) => {
    try {
      const conversation = await chat.direct(employee.id);
      await loadConversations();
      setSelected(conversation);
      setSearchQuery('');
      setPeople([]);
      setNewMessageOpen(false);
    } catch (caught) {
      setError(errorMessage(caught, 'Unable to start a conversation.'));
    }
  };

  const sendMessage = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const content = composer.trim();
    if (!selected || !content || sending) return;
    setSending(true);
    setError('');
    try {
      const message = await chat.send(selected.id, content);
      stickToBottom.current = true;
      setMessages((current) => current.some((item) => item.id === message.id) ? current : [...current, message]);
      setComposer('');
      await loadConversations();
    } catch (caught) {
      setError(errorMessage(caught, 'Unable to send message.'));
    } finally {
      setSending(false);
    }
  };

  const onComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  };

  const onMessageScroll = () => {
    const region = messageRegion.current;
    if (!region) return;
    stickToBottom.current = region.scrollHeight - region.scrollTop - region.clientHeight < 84;
  };

  const groupedMessages = useMemo(() => groupMessages(messages), [messages]);
  const selectedTitle = selected ? conversationTitle(selected) : '';

  return <main className={'workspace-page chat-workspace ' + (selected ? 'chat-selected' : '')}>
    <header className="page-header chat-page-header"><div><p className="eyebrow">Workplace messaging</p><h1>Chat</h1></div><ConnectionIndicator state={connectionState} /></header>
    {error && <div className="chat-page-error error" role="alert"><CircleAlert size={17} aria-hidden="true" /><span>{error}</span><button type="button" className="button-secondary button-small" onClick={() => setError('')}>Dismiss</button></div>}
    <section className="chat-shell" aria-label="Workplace chat">
      <aside className="conversation-panel" aria-label="Conversations">
        <div className="conversation-panel-header"><div><h2>Messages</h2><p>{conversationsLoading ? 'Loading conversations…' : String(conversations.length) + ' conversation' + (conversations.length === 1 ? '' : 's')}</p></div><button type="button" className="new-message-button" aria-label="Start a new message" aria-expanded={newMessageOpen} onClick={() => { setNewMessageOpen((open) => !open); setSearchQuery(''); setPeople([]); }}><Plus size={18} aria-hidden="true" /><span>New</span></button></div>
        {newMessageOpen && <div className="new-message-search"><div className="search-field"><Search size={16} aria-hidden="true" /><label className="sr-only" htmlFor="employee-search">Search employees</label><input id="employee-search" autoFocus value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="Search employees" /></div><button type="button" className="search-close" aria-label="Close new message search" onClick={() => { setNewMessageOpen(false); setSearchQuery(''); setPeople([]); }}><X size={17} /></button><div className="employee-results" aria-live="polite">{searchLoading ? <p className="search-state"><LoaderCircle size={15} className="spin" /> Searching employees…</p> : searchQuery.trim().length >= 2 && people.length === 0 ? <p className="search-state">No employees found.</p> : people.map((person) => <button type="button" key={person.id} className="employee-result" onClick={() => void startDirect(person)}><span className="person-avatar" aria-hidden="true">{initials(person.full_name)}</span><span><strong>{person.full_name}</strong><small>{person.employee_code}{person.designation ? ' · ' + person.designation : ''}</small></span></button>)}</div></div>}
        <div className="conversation-list">{conversationsLoading ? <ConversationListLoading /> : conversations.length === 0 ? <div className="conversation-empty"><MessageCircle size={22} aria-hidden="true" /><p>No conversations yet.</p><small>Start a message to connect with a colleague.</small></div> : conversations.map((conversation) => <button type="button" key={conversation.id} className={'conversation-row ' + (selected?.id === conversation.id ? 'selected' : '')} onClick={() => { setError(''); setSelected(conversation); }}><ConversationAvatar conversation={conversation} /><span className="conversation-row-content"><span className="conversation-row-title"><strong>{conversationTitle(conversation)}</strong>{conversation.unread_count > 0 && <b className="badge">{conversation.unread_count > 99 ? '99+' : conversation.unread_count}</b>}</span><small>{conversation.last_message?.content || (conversation.type === 'GROUP' ? 'Group conversation' : 'No messages yet')}</small></span></button>)}</div>
      </aside>
      <section className="active-chat" aria-label={selected ? selectedTitle : 'Selected conversation'}>
        {!selected ? <div className="chat-empty-state"><span className="chat-empty-icon"><MessageCircle size={28} /></span><h2>Select a conversation</h2><p>Choose a message from the list or start a new conversation with an employee.</p><button type="button" className="button-secondary" onClick={() => setNewMessageOpen(true)}><Plus size={16} /> New message</button></div> : <>
          <header className="active-chat-header"><button className="chat-back-button" type="button" onClick={() => setSelected(null)}><ChevronLeft size={18} /> Back</button><ConversationAvatar conversation={selected} /><div><h2>{selectedTitle}</h2><p>{selected.type === 'GROUP' ? 'Group conversation' : 'Direct conversation'}</p></div><ConnectionIndicator state={connectionState} /></header>
          {historyError ? <div className="history-state"><CircleAlert size={18} /><p>{historyError}</p><button type="button" className="button-secondary button-small" onClick={() => void loadMessages(selected)}>Try again</button></div> : <div className="message-region" ref={messageRegion} onScroll={onMessageScroll} aria-live="polite">{historyLoading ? <MessageLoading /> : groupedMessages.length === 0 ? <div className="messages-empty"><MessageCircle size={22} aria-hidden="true" /><p>No messages yet.</p><small>Send a message to start the conversation.</small></div> : groupedMessages.map((group) => <MessageGroupView key={group.senderId + '-' + group.messages[0].id} group={group} mine={group.senderId === user?.id} />)}</div>}
          <form className="chat-composer" onSubmit={sendMessage}><label className="sr-only" htmlFor="chat-message">Message</label><textarea id="chat-message" value={composer} maxLength={4000} rows={2} onChange={(event) => setComposer(event.target.value)} onKeyDown={onComposerKeyDown} placeholder="Write a message…" disabled={sending || !!historyError} /><div><small>Enter to send · Shift + Enter for a new line</small><button type="submit" disabled={!composer.trim() || sending || !!historyError}>{sending ? <><LoaderCircle size={16} className="spin" /> Sending</> : <><Send size={16} /> Send</>}</button></div></form>
        </>}
      </section>
    </section>
  </main>;
}

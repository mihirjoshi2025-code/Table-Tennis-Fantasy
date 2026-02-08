import { useState, useRef, useEffect } from 'react';
import { adviseRoles, type RoleAdvisorResponse, type RoleRecommendation } from '../api';
import '../App.css';

export interface RoleAdvisorBubbleProps {
  /** Current gender so the advisor can scope recommendations (e.g. men/women pool). */
  gender: 'men' | 'women';
  /** Optional team id if user is editing an existing team (not used on create page). */
  teamId?: string | null;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  response?: RoleAdvisorResponse;
}

export default function RoleAdvisorBubble({ gender, teamId }: RoleAdvisorBubbleProps) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    const query = input.trim();
    if (!query || loading) return;
    setInput('');
    setError(null);
    const userMsg: ChatMessage = { id: crypto.randomUUID(), role: 'user', text: query };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);
    try {
      const response = await adviseRoles({ query, gender, team_id: teamId ?? undefined });
      const assistantMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        text: response.explanation,
        response,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed');
      const errMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        text: e instanceof Error ? e.message : 'Something went wrong. Make sure the API is running and OPENAI_API_KEY is set for full advice.',
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <>
      <button
        type="button"
        className="role-advisor-bubble"
        onClick={() => setOpen((o) => !o)}
        aria-label="Open role advisor"
        aria-expanded={open}
      >
        <span className="role-advisor-bubble-icon" aria-hidden>💬</span>
        <span className="role-advisor-bubble-label">AI Coach</span>
      </button>

      {open && (
        <div className="role-advisor-panel" role="dialog" aria-label="Role advisor chat">
          <div className="role-advisor-panel-header">
            <h3 className="role-advisor-panel-title">Role advisor</h3>
            <button
              type="button"
              className="role-advisor-panel-close"
              onClick={() => setOpen(false)}
              aria-label="Close"
            >
              ×
            </button>
          </div>
          <p className="role-advisor-panel-hint">
            Ask which players suit which roles, e.g. &quot;Who should I assign as my Aggressor?&quot;
          </p>
          <div className="role-advisor-messages">
            {messages.length === 0 && (
              <p className="role-advisor-placeholder">Ask a question about players and roles…</p>
            )}
            {messages.map((msg) => (
              <div key={msg.id} className={`role-advisor-msg role-advisor-msg-${msg.role}`}>
                <div className="role-advisor-msg-text">{msg.text}</div>
                {msg.response && msg.response.recommendations.length > 0 && (
                  <div className="role-advisor-recommendations">
                    {msg.response.recommendations.map((r: RoleRecommendation, i: number) => (
                      <div key={i} className="role-advisor-rec">
                        <strong>{r.player_name}</strong> → {r.suggested_role}
                        <div className="role-advisor-rec-why">{r.why_fit}</div>
                        {r.risk && <div className="role-advisor-rec-risk">Risk: {r.risk}</div>}
                      </div>
                    ))}
                  </div>
                )}
                {msg.response?.tradeoffs && (
                  <div className="role-advisor-tradeoffs">{msg.response.tradeoffs}</div>
                )}
              </div>
            ))}
            {loading && (
              <div className="role-advisor-msg role-advisor-msg-assistant">
                <div className="role-advisor-msg-text">Thinking…</div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
          {error && <p className="role-advisor-error">{error}</p>}
          <div className="role-advisor-input-row">
            <input
              ref={inputRef}
              type="text"
              className="role-advisor-input"
              placeholder="Ask about players and roles…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
            />
            <button
              type="button"
              className="btn-primary role-advisor-send"
              onClick={handleSend}
              disabled={loading || !input.trim()}
            >
              Send
            </button>
          </div>
        </div>
      )}
    </>
  );
}

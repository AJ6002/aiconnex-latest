import React, { useState, useEffect, useRef } from 'react';

interface ChatBotModalProps {
  isOpen: boolean;
  onClose: () => void;
  userId?: string;
  onNavigateView?: (viewId: string) => void;
  isDocked?: boolean;
  onDockChange?: (docked: boolean) => void;
  onSessionCreated?: (sessionId: string) => void;
  onUploadRequested?: () => void;
  externalNarration?: string | null;
  interruptData?: any;
  onInterruptResolved?: () => void;
  activeSessionId?: string | null;
}

interface Message {
  sender: 'user' | 'bot';
  text: string;
  html?: string;
  intent?: string;
  time: string;
  quickAction?: { label: string; viewId: string };
  options?: string[];
  isInterrupt?: boolean;
}

function renderMarkdownToHtml(md: string): string {
  if (!md) return '';

  let html = md;

  // 1. Code blocks (```lang ... ```)
  const codeBlocks: string[] = [];
  html = html.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (_match, lang, code) => {
    const placeholder = `__CODE_BLOCK_${codeBlocks.length}__`;
    const escapedCode = code
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
    codeBlocks.push(
      `<div class="my-2.5 rounded-lg overflow-hidden border border-slate-700 bg-slate-900 shadow-md">` +
      `<div class="flex items-center justify-between px-3 py-1 bg-slate-800 border-b border-slate-700 text-[10px] font-mono text-slate-400">` +
      `<span>${lang || 'code'}</span>` +
      `</div>` +
      `<pre class="p-3 text-[11px] font-mono text-emerald-400 overflow-x-auto leading-relaxed whitespace-pre"><code>${escapedCode.trim()}</code></pre>` +
      `</div>`
    );
    return placeholder;
  });

  // 2. Tables (| col | col |\n|---|---|\n| val | val |)
  const tables: string[] = [];
  const tableRegex = /((?:\|[^\n]+\|\r?\n)+)/g;
  html = html.replace(tableRegex, (tableBlock) => {
    const lines = tableBlock.trim().split('\n').map(l => l.trim()).filter(Boolean);
    if (lines.length < 2) return tableBlock;

    const isSeparator = (line: string) => /^\|(?:\s*:?-+:?\s*\|)+$/.test(line);

    let headerHtml = '';
    let bodyHtml = '';

    const formatInline = (text: string) => {
      return text
        .replace(/\*\*([^*]+)\*\*/g, '<strong class="font-semibold text-slate-900">$1</strong>')
        .replace(/\*([^*]+)\*/g, '<em class="italic text-slate-800">$1</em>')
        .replace(/`([^`]+)`/g, '<code class="bg-slate-100 text-[#E86326] px-1 py-0.5 rounded font-mono text-[10px] border border-slate-200">$1</code>');
    };

    const parseRow = (line: string, isTh = false) => {
      const cells = line.split('|').slice(1, -1);
      const tag = isTh ? 'th' : 'td';
      const cellClass = isTh 
        ? 'px-3 py-1.5 font-bold text-slate-800 bg-slate-100 border border-slate-300 text-left text-[11px]' 
        : 'px-3 py-1.5 text-slate-700 border border-slate-200 text-left text-[11px]';
      return `<tr>${cells.map(c => `<${tag} class="${cellClass}">${formatInline(c.trim())}</${tag}>`).join('')}</tr>`;
    };

    if (lines.length >= 2 && isSeparator(lines[1])) {
      headerHtml = `<thead>${parseRow(lines[0], true)}</thead>`;
      bodyHtml = `<tbody>${lines.slice(2).map(l => parseRow(l, false)).join('')}</tbody>`;
    } else {
      bodyHtml = `<tbody>${lines.map(l => parseRow(l, false)).join('')}</tbody>`;
    }

    const placeholder = `__TABLE_BLOCK_${tables.length}__`;
    tables.push(
      `<div class="my-2.5 overflow-x-auto rounded-lg border border-slate-200 shadow-xs bg-white">` +
      `<table class="w-full text-left border-collapse">${headerHtml}${bodyHtml}</table>` +
      `</div>`
    );
    return placeholder;
  });

  // 3. Headings (###, ##, #)
  html = html.replace(/^### (.*$)/gim, '<h4 class="font-bold text-xs text-slate-800 mt-2 mb-1">$1</h4>');
  html = html.replace(/^## (.*$)/gim, '<h3 class="font-bold text-sm text-slate-900 mt-2.5 mb-1">$1</h3>');
  html = html.replace(/^# (.*$)/gim, '<h2 class="font-bold text-base text-slate-900 mt-3 mb-1.5">$1</h2>');

  // 3. Bold (**text** or __text__)
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold text-slate-900">$1</strong>');
  html = html.replace(/__(.*?)__/g, '<strong class="font-semibold text-slate-900">$1</strong>');

  // 4. Italic (*text* or _text_)
  html = html.replace(/\*(.*?)\*/g, '<em class="italic text-slate-700">$1</em>');
  html = html.replace(/_(.*?)_/g, '<em class="italic text-slate-700">$1</em>');

  // 5. Inline code (`code`)
  html = html.replace(/`([^`]+)`/g, '<code class="bg-slate-100 text-amber-700 px-1.5 py-0.5 rounded text-[11px] font-mono border border-slate-200">$1</code>');

  // 6. Blockquotes (> text)
  html = html.replace(/^> (.*$)/gim, '<blockquote class="border-l-2 border-amber-500 pl-3 py-1 my-1.5 text-slate-600 bg-amber-50/50 rounded-r text-xs italic">$1</blockquote>');

  // 7. Unordered lists (* or - items)
  html = html.replace(/^[\*\-] (.*$)/gim, '<li class="ml-4 list-disc text-xs text-slate-700 my-0.5">$1</li>');

  // 8. Ordered lists (1. items)
  html = html.replace(/^\d+\. (.*$)/gim, '<li class="ml-4 list-decimal text-xs text-slate-700 my-0.5">$1</li>');

  // 9. Paragraph breaks (double newlines)
  html = html.replace(/\n\n+/g, '</p><p class="my-1.5">');

  // 10. Single newlines to line breaks (preserving intentional spacing)
  html = html.replace(/\n/g, '<br/>');

  // Restore code blocks
  codeBlocks.forEach((block, idx) => {
    html = html.replace(`__CODE_BLOCK_${idx}__`, block);
  });

  return `<p class="my-1">${html}</p>`;
}

export const ChatBotModal: React.FC<ChatBotModalProps> = ({
  isOpen,
  onClose,
  userId: initialUserId = '1223',
  onNavigateView,
  isDocked,
  onDockChange,
  onSessionCreated,
  onUploadRequested,
  externalNarration,
  externalNarrationNode,
  interruptData,
  onInterruptResolved,
  activeSessionId,
}) => {
  const [userId, setUserId] = useState(initialUserId);
  const [isMinimizedLocal, setIsMinimizedLocal] = useState(false);
  const isMinimized = isDocked !== undefined ? isDocked : isMinimizedLocal;
  const [inputText, setInputText] = useState('');
  const [messages, setMessages] = useState<Message[]>([
    {
      sender: 'bot',
      text: "Hi there! I'm Jane, Lead Machine Learning Solutions Architect at AIConnex. I'd love to help you build and launch your custom AutoML project! What prediction goal or dataset are you working with today?",
      html: renderMarkdownToHtml("Hi there! I'm **Jane**, Lead Machine Learning Solutions Architect at AIConnex. I'd love to help you build and launch your custom AutoML project! What prediction goal or dataset are you working with today?"),
      intent: 'Jane — Lead ML Architect',
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    },
  ]);
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Handle live external narration injected from Compiler or Pipeline SSE
  useEffect(() => {
    if (externalNarration && externalNarration.trim()) {
      const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      
      let intentBadge = 'Compiler • Live';
      if (externalNarrationNode) {
        const formatted = externalNarrationNode
          .replace(/_node$/, '')
          .split('_')
          .map((w: string) => w.charAt(0).toUpperCase() + w.slice(1))
          .join(' ');
        intentBadge = `Scout • ${formatted}`;
      }

      const narrationMsg: Message = {
        sender: 'bot',
        text: externalNarration,
        html: renderMarkdownToHtml(externalNarration),
        intent: intentBadge,
        time: timeStr,
      };
      setMessages((prev) => [...prev, narrationMsg]);
    }
  }, [externalNarration, externalNarrationNode]);

  // Handle interactive clarification interrupt events from LangGraph
  useEffect(() => {
    if (interruptData) {
      let questionText = "";
      if (interruptData.questions && Array.isArray(interruptData.questions)) {
        questionText = interruptData.questions.join("\n\n");
      } else if (interruptData.question) {
        questionText = String(interruptData.question);
      } else if (interruptData.message) {
        questionText = String(interruptData.message);
      } else {
        questionText = "Clarification needed: Please select an option to proceed.";
      }

      const options: string[] = Array.isArray(interruptData.options) ? interruptData.options : [];
      const htmlContent = interruptData.question_html || renderMarkdownToHtml(questionText);

      const interruptMsg: Message = {
        sender: 'bot',
        text: questionText,
        html: htmlContent,
        intent: 'Clarification Checkpoint',
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        options: options,
        isInterrupt: true,
      };

      setMessages((prev) => [...prev, interruptMsg]);
    }
  }, [interruptData]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    if (isOpen) {
      scrollToBottom();
    }
  }, [messages, isOpen]);

  if (!isOpen) return null;

  const handleSendMessage = async (textToSend?: string) => {
    const query = textToSend || inputText;
    if (!query.trim() || isLoading) return;

    const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const userMsg: Message = { sender: 'user', text: query, time: timeStr };

    setMessages((prev) => [...prev, userMsg]);
    if (!textToSend) setInputText('');
    setIsLoading(true);

    try {
      // Send request to Jane Chatbot API gateway (port 8000 or 5000) or fallback
      const bodyPayload = {
        userId,
        session_id: activeSessionId || undefined,
        sessionId: activeSessionId || undefined,
        message: query,
        query,
      };

      let response: Response | null = null;
      try {
        response = await fetch('http://localhost:8000/api/v1/jane/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(bodyPayload),
        });
      } catch {
        try {
          response = await fetch('http://localhost:5000/api/v1/jane/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(bodyPayload),
          });
        } catch {
          try {
            response = await fetch('/api/v1/jane/chat', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(bodyPayload),
            });
          } catch {
            // offline
          }
        }
      }

      if (response && response.ok) {
        const data = await response.json();
        const rawText = data.reply || data.response || data.botResponse || data.answer || "No response received from Jane.";
        const botMsg: Message = {
          sender: 'bot',
          text: rawText,
          html: data.reply_html || data.html || renderMarkdownToHtml(rawText),
          intent: data.intent ? `Intent: ${data.intent}` : 'Jane • AI Assistant',
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          options: data.options || [],
        };
        setMessages((prev) => [...prev, botMsg]);

        // Propagate active LangGraph / Jane session ID
        if (data.session_id && onSessionCreated) {
          onSessionCreated(data.session_id);
        }

        // Automatic seamless transition: slide & dock Jane, then open upload dropzone
        if (data.action_required === 'OPEN_UPLOAD_CONTROLLER') {
          setTimeout(() => {
            if (onUploadRequested) {
              onUploadRequested();
            }
          }, 1000);
        }
      } else {
        throw new Error('API offline');
      }
    } catch {
      // Backend is offline — show a clean, helpful notice instead of fake data
      setTimeout(() => {
        const offlineText = '⚠️ **Jane API Server is Offline.**\n\nUnable to reach the Jane Assistant backend on `http://localhost:8000` or `http://localhost:5000`.\n\nTo start the backend server, run in your terminal:\n```bash\npython backend/app.py\n```\nThen retry your question!';
        setMessages((prev) => [
          ...prev,
          {
            sender: 'bot',
            text: offlineText,
            intent: 'BACKEND_OFFLINE',
            time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
        ]);
      }, 300);
    } finally {
      setIsLoading(false);
    }
  };

  const handleClarificationChoice = async (choice: string) => {
    if (isLoading) return;
    if (interruptData) {
      const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const userMsg: Message = { sender: 'user', text: choice, time: timeStr };
      setMessages((prev) => [...prev, userMsg]);
      setIsLoading(true);

      try {
        const targetSession = activeSessionId || 'default_session';
        const bodyPayload = {
          userId,
          session_id: targetSession,
          message: choice,
          user_input: choice,
        };

        let response = await fetch('http://localhost:8000/api/agent/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(bodyPayload),
        }).catch(() => null);

        if (!response || !response.ok) {
          response = await fetch('http://localhost:5000/api/agent/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(bodyPayload),
          }).catch(() => null);
        }

        if (response && response.ok) {
          const reader = response.body?.getReader();
          const decoder = new TextDecoder();
          if (reader) {
            let buffer = '';
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;
              buffer += decoder.decode(value, { stream: true });
              const lines = buffer.split('\n');
              buffer = lines.pop() || '';

              for (const line of lines) {
                if (line.startsWith('data: ')) {
                  try {
                    const eventData = JSON.parse(line.slice(6));
                    if (eventData.type === 'text' && eventData.delta) {
                      setMessages((prev) => [
                        ...prev,
                        {
                          sender: 'bot',
                          text: eventData.delta,
                          html: renderMarkdownToHtml(eventData.delta),
                          intent: 'Compiler • Resumed',
                          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                        },
                      ]);
                    }
                    if (eventData.type === 'interrupt' && eventData.payload) {
                      const qText = Array.isArray(eventData.payload.questions)
                        ? eventData.payload.questions.join('\n\n')
                        : (eventData.payload.question || eventData.payload.message || 'Clarification needed');
                      setMessages((prev) => [
                        ...prev,
                        {
                          sender: 'bot',
                          text: qText,
                          html: eventData.payload.question_html || renderMarkdownToHtml(qText),
                          intent: 'Clarification Checkpoint',
                          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                          options: eventData.payload.options || [],
                          isInterrupt: true,
                        },
                      ]);
                    }
                  } catch {}
                }
              }
            }
          }
          if (onInterruptResolved) {
            onInterruptResolved();
          }
        }
      } catch (err) {
        console.error('[ChatBotModal] Failed to submit clarification:', err);
      } finally {
        setIsLoading(false);
      }
    } else {
      // Conversational clarification chip click
      await handleSendMessage(choice);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className={`transition-all duration-300 pointer-events-auto z-[100] ${
        isMinimized
          ? 'fixed bottom-6 right-6'
          : 'fixed inset-0 flex items-center justify-center p-4 sm:p-6'
      }`}
    >
      {/* Frosted/Wet Glass Backdrop (only shown when expanded in center) */}
      {!isMinimized && (
        <div
          className="absolute inset-0 bg-slate-900/20 backdrop-blur-[4px] transition-all duration-300"
          onClick={onClose}
        />
      )}

      {/* Floating Chatbot Window */}
      <div
        className={`relative bg-white/95 backdrop-blur-md border border-slate-200/80 rounded-3xl shadow-[0_24px_60px_rgba(13,21,51,0.28)] transition-all duration-300 flex flex-col overflow-hidden z-10 ${
          isMinimized
            ? 'w-[360px] h-[415px] rounded-2xl shadow-2xl border-2 border-[#0D1533]/20'
            : 'w-full max-w-lg h-[600px]'
        }`}
      >
        {/* Header (Deep Indigo #2B0063) */}
        <div className="bg-[#2B0063] px-4 py-3 flex justify-between items-center text-white shadow-md flex-shrink-0">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-8 h-8 rounded-full bg-[#E86326]/20 flex items-center justify-center text-[#E86326] border border-[#E86326]/40 shadow-sm flex-shrink-0">
              <span className="material-symbols-outlined text-lg" style={{ fontVariationSettings: "'FILL' 1" }}>
                smart_toy
              </span>
            </div>
            <div className="min-w-0">
              <h3 className="font-bold text-xs sm:text-sm leading-tight text-white truncate flex items-center gap-1.5">
                <span>Jane — AI Assistant & Copilot</span>
              </h3>
              <span className="text-[10px] text-slate-300 block font-mono truncate">
                Logging: user-intent-{userId}.json
              </span>
            </div>
          </div>

          <div className="flex items-center gap-1.5 flex-shrink-0">
            {!isMinimized && (
              <input
                type="text"
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
                title="User ID"
                className="w-11 bg-white/10 text-white border border-white/20 rounded px-1 py-0.5 text-[10px] font-mono text-center focus:outline-none focus:border-[#E86326]"
                placeholder="ID"
              />
            )}

            {/* Minimize / Expand Toggle */}
            <button
              onClick={() => {
                if (onDockChange) {
                  onDockChange(!isMinimized);
                } else {
                  setIsMinimizedLocal(!isMinimizedLocal);
                }
              }}
              title={isMinimized ? 'Expand to full size' : 'Minimize to bottom-right'}
              className="w-7 h-7 rounded-full hover:bg-white/10 flex items-center justify-center text-slate-300 hover:text-white transition-colors"
            >
              <span className="material-symbols-outlined text-base">
                {isMinimized ? 'open_in_full' : 'remove'}
              </span>
            </button>

            {/* Close Button */}
            <button
              onClick={onClose}
              title="Close chat"
              className="w-7 h-7 rounded-full hover:bg-red-500/20 hover:text-red-300 flex items-center justify-center text-slate-300 transition-colors"
            >
              <span className="material-symbols-outlined text-base">close</span>
            </button>
          </div>
        </div>

        {/* Content Body */}
        <div className="flex-1 flex flex-col justify-between overflow-hidden bg-slate-50">
          {/* Messages Thread */}
          <div className="flex-1 overflow-y-auto p-3.5 space-y-3">
            {messages.map((msg, idx) => (
              <div
                key={idx}
                className={`flex flex-col ${msg.sender === 'user' ? 'items-end' : 'items-start'}`}
              >
                <div
                  className={`max-w-[88%] p-3 rounded-2xl shadow-xs text-xs space-y-1.5 relative ${
                    msg.sender === 'user'
                      ? 'bg-[#E86326] text-white rounded-br-none'
                      : 'bg-white border border-slate-200 text-[#333333] rounded-bl-none'
                  }`}
                >
                  {msg.sender === 'bot' && (
                    <div className="flex items-center gap-1.5 mb-1">
                      <span className="w-2 h-2 rounded-full bg-[#E86326] animate-pulse"></span>
                      <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-slate-600">
                        {msg.intent || 'RAG Active'}
                      </span>
                    </div>
                  )}
                  {msg.html ? (
                    <div
                      className="jane-markdown-prose leading-relaxed text-xs space-y-1.5"
                      dangerouslySetInnerHTML={{ __html: msg.html }}
                    />
                  ) : (
                    <p className="leading-relaxed whitespace-pre-wrap">{msg.text}</p>
                  )}

                  {/* Interactive Clarification Option Chips */}
                  {msg.options && msg.options.length > 0 && (
                    <div className="mt-2.5 pt-2 border-t border-slate-100 flex flex-wrap gap-1.5">
                      <span className="text-[10px] font-semibold text-slate-500 w-full mb-0.5">Select option:</span>
                      {msg.options.map((opt, oIdx) => (
                        <button
                          key={oIdx}
                          onClick={() => handleClarificationChoice(opt)}
                          className="clarification-chip-btn"
                          title={`Select ${opt}`}
                        >
                          <span className="material-symbols-outlined text-[11px] text-[#FF6B35]">check_circle</span>
                          <span>{opt}</span>
                        </button>
                      ))}
                    </div>
                  )}

                  {msg.quickAction && (
                    <button
                      onClick={() => {
                        if (onNavigateView && msg.quickAction) {
                          onNavigateView(msg.quickAction.viewId);
                          onClose();
                        }
                      }}
                      className="mt-1.5 px-2.5 py-1 bg-[#E86326] hover:bg-[#D5521B] text-white font-bold text-[11px] rounded-full shadow-xs flex items-center gap-1 transition-all"
                    >
                      <span>{msg.quickAction.label}</span>
                      <span className="material-symbols-outlined text-xs">arrow_forward</span>
                    </button>
                  )}
                </div>
                <span className="text-[9px] text-slate-400 font-mono mt-0.5 px-1">{msg.time}</span>
              </div>
            ))}

            {isLoading && (
              <div className="flex items-center gap-2 text-slate-400 text-xs font-mono p-1.5">
                <span className="w-2 h-2 rounded-full bg-[#0D1533] animate-ping"></span>
                <span>Jane is processing query...</span>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Quick Prompt Chips */}
          <div className="px-3 py-1.5 bg-white border-t border-slate-200 flex gap-1.5 overflow-x-auto no-scrollbar">
            <button
              onClick={() => handleSendMessage('Predict RUL for Turbine Asset')}
              className="px-2.5 py-1 bg-slate-100 hover:bg-[#E86326] hover:text-white text-slate-700 font-medium text-[11px] rounded-full transition-all border border-slate-200 whitespace-nowrap"
            >
              Predict RUL
            </button>
            <button
              onClick={() => handleSendMessage('Train AutoML Model on Cluster 1')}
              className="px-2.5 py-1 bg-slate-100 hover:bg-[#E86326] hover:text-white text-slate-700 font-medium text-[11px] rounded-full transition-all border border-slate-200 whitespace-nowrap"
            >
              Train AutoML
            </button>
            <button
              onClick={() => handleSendMessage('Check Telemetry Status')}
              className="px-2.5 py-1 bg-slate-100 hover:bg-[#E86326] hover:text-white text-slate-700 font-medium text-[11px] rounded-full transition-all border border-slate-200 whitespace-nowrap"
            >
              Telemetry Status
            </button>
          </div>

          {/* Input Form */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSendMessage();
            }}
            className="p-2.5 bg-white border-t border-slate-200 flex items-center gap-2"
          >
            <div className="relative flex-1">
              <input
                type="text"
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                placeholder="Ask AI Copilot or type a command..."
                className="w-full pl-3.5 pr-9 py-2 bg-slate-50 border border-slate-300 rounded-full text-xs text-[#333333] focus:outline-none focus:border-[#2B0063] focus:ring-1 focus:ring-[#2B0063]"
              />
              <button
                type="submit"
                disabled={!inputText.trim()}
                className="absolute right-1.5 top-1/2 -translate-y-1/2 w-7 h-7 rounded-full bg-[#E86326] text-white hover:bg-[#D5521B] disabled:opacity-30 flex items-center justify-center transition-all"
              >
                <span className="material-symbols-outlined text-xs font-bold">send</span>
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};

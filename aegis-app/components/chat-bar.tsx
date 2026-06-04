"use client";

import { useRef, useState } from "react";
import { RiSendPlaneFill, RiCloseLine } from "@remixicon/react";
import ReactMarkdown from "react-markdown";

interface Message {
  role: "user" | "assistant";
  content: string;
}

export function ChatBar() {
  const [query, setQuery] = useState("");
  const [focused, setFocused] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const handleSend = async () => {
    const text = query.trim();
    if (!text || loading) return;

    const userMsg: Message = { role: "user", content: text };
    const updated = [...messages, userMsg];
    setMessages(updated);
    setQuery("");
    setOpen(true);
    setLoading(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: updated }),
      });
      const data = await res.json();
      const assistantMsg: Message = {
        role: "assistant",
        content: data.reply ?? data.error ?? "Something went wrong.",
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Failed to reach AEGIS AI. Please try again." },
      ]);
    } finally {
      setLoading(false);
      setTimeout(() => {
        scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
      }, 50);
    }
  };

  const handleClose = () => {
    setOpen(false);
    setMessages([]);
  };

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 flex flex-col items-center px-4 pb-3 pt-2 pointer-events-none">
      <div className="w-full max-w-2xl pointer-events-auto">
        {/* Chat panel */}
        {open && messages.length > 0 && (
          <div className="mb-2 flex flex-col rounded-2xl border border-zinc-700 bg-zinc-900 shadow-xl shadow-black/40">
            <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-2">
              <span className="text-xs font-medium text-zinc-400">AEGIS AI</span>
              <button
                onClick={handleClose}
                className="text-zinc-500 hover:text-zinc-300 transition-colors"
              >
                <RiCloseLine className="size-4" />
              </button>
            </div>
            <div
              ref={scrollRef}
              className="flex max-h-80 flex-col gap-3 overflow-y-auto px-4 py-3 scrollbar-thin"
            >
              {messages.map((msg, i) => (
                <div
                  key={i}
                  className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[85%] rounded-xl px-3 py-2 text-sm leading-relaxed ${
                      msg.role === "user"
                        ? "bg-zinc-700 text-zinc-100"
                        : "bg-zinc-800 text-zinc-300"
                    }`}
                  >
                    {msg.role === "user" ? (
                      <p className="whitespace-pre-wrap">{msg.content}</p>
                    ) : (
                      <div className="prose prose-sm prose-invert max-w-none prose-headings:text-zinc-200 prose-headings:text-sm prose-headings:font-semibold prose-headings:mt-3 prose-headings:mb-1 prose-p:my-1 prose-ul:my-1 prose-ol:my-1 prose-li:my-0.5 prose-strong:text-zinc-200 prose-code:text-amber-300 prose-code:bg-zinc-900 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-pre:bg-zinc-950 prose-pre:rounded-lg prose-pre:text-xs">
                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {loading && (
                <div className="flex justify-start">
                  <div className="rounded-xl bg-zinc-800 px-3 py-2 text-sm text-zinc-500">
                    Thinking...
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Input bar */}
        <div className="flex items-center gap-2 rounded-full border border-zinc-700 bg-zinc-900 px-4 py-2.5 shadow-lg shadow-black/30">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="Ask me anything about Battle Strategies, Analysis and Observability..."
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            className="flex-1 bg-transparent text-sm text-zinc-100 placeholder:text-zinc-500 outline-none"
          />
          <button
            onClick={handleSend}
            className="flex size-8 shrink-0 items-center justify-center rounded-full bg-white text-black transition-opacity hover:opacity-80 disabled:opacity-40"
            disabled={!query.trim() || loading}
          >
            <RiSendPlaneFill className="size-4" />
          </button>
        </div>
        <p className={`mt-2 text-center text-xs text-zinc-500 ${focused ? "opacity-100" : "opacity-0"}`}>
          AEGIS AI is powered by OpenRouter with knowledge base from AEGIS Repo
        </p>
      </div>
    </div>
  );
}

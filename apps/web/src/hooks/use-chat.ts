"use client";

import { useCallback, useRef, useState } from "react";

import { api, errorMessage, redirectToLogin } from "@/lib/api";
import { readSSE } from "@/lib/sse";
import type { ChatMessage, Source, StoredMessage } from "@/lib/types";

const uid = () => crypto.randomUUID();

export function useChat(tenantId: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const send = useCallback(
    async (question: string) => {
      const text = question.trim();
      if (!text || busy) return;

      const assistantId = uid();
      setMessages((prev) => [
        ...prev,
        { id: uid(), role: "user", content: text, sources: [], citations: [], status: "done" },
        { id: assistantId, role: "assistant", content: "", sources: [], citations: [], status: "streaming" },
      ]);
      setBusy(true);

      const update = (patch: Partial<ChatMessage> | ((m: ChatMessage) => Partial<ChatMessage>)) =>
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, ...(typeof patch === "function" ? patch(m) : patch) } : m)),
        );

      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const res = await fetch(`/api/proxy/tenants/${tenantId}/ask`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question: text, conversation_id: conversationId }),
          signal: controller.signal,
        });
        if (res.status === 401) return redirectToLogin();
        if (!res.ok || !res.body) {
          const data = await res.json().catch(() => null);
          update({ status: "error", error: errorMessage(data, "No se pudo procesar la consulta."), retryable: true });
          return;
        }

        for await (const { event, data } of readSSE(res.body)) {
          const payload = data as Record<string, unknown>;
          if (event === "sources") {
            setConversationId(payload.conversation_id as string);
            update({ sources: payload.sources as Source[], searchQuery: payload.search_query as string });
          } else if (event === "token") {
            update((m) => ({ content: m.content + (payload.text as string) }));
          } else if (event === "done") {
            update({ status: "done", citations: payload.citations as number[] });
          } else if (event === "error") {
            update({ status: "error", error: payload.message as string, retryable: payload.retryable as boolean });
          }
        }
        // Stream cerrado sin "done" ni "error" (p. ej. caída de red a mitad)
        update((m) => (m.status === "streaming" ? { status: "error", error: "La respuesta se interrumpió.", retryable: true } : {}));
      } catch (e) {
        if ((e as Error).name === "AbortError") update({ status: "done" });
        else update({ status: "error", error: "Se perdió la conexión con el servidor.", retryable: true });
      } finally {
        abortRef.current = null;
        setBusy(false);
      }
    },
    [busy, conversationId, tenantId],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  const retry = useCallback(() => {
    // Reenvía la última pregunta: se quitan la pregunta y la respuesta fallida
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (!lastUser) return;
    setMessages((prev) => prev.slice(0, prev.lastIndexOf(lastUser)));
    void send(lastUser.content);
  }, [messages, send]);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setConversationId(null);
  }, []);

  const load = useCallback(
    async (id: string) => {
      abortRef.current?.abort();
      setLoadingHistory(true);
      try {
        const stored = await api<StoredMessage[]>(`/tenants/${tenantId}/conversations/${id}/messages`);
        setConversationId(id);
        setMessages(
          stored.map((m) => ({
            id: m.id,
            role: m.role,
            content: m.content,
            sources: m.citations,
            citations: m.citations.map((c) => c.n),
            status: "done",
          })),
        );
      } finally {
        setLoadingHistory(false);
      }
    },
    [tenantId],
  );

  return { messages, conversationId, busy, loadingHistory, send, stop, retry, reset, load };
}

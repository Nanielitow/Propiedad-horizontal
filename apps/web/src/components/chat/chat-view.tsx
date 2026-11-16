"use client";

import { Loader2, SquarePen } from "lucide-react";
import { useEffect, useRef } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { Button } from "@/components/ui/button";
import { useChat } from "@/hooks/use-chat";

import { AssistantMessage } from "./assistant-message";
import { Composer } from "./composer";
import { ChatEmptyState } from "./empty-state";
import { HistoryMenu } from "./history-menu";

export function ChatView() {
  const { tenant } = useTenant();
  const chat = useChat(tenant.tenant_id);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);

  // Auto-desplazamiento mientras llega la respuesta, salvo que el usuario haya
  // subido a leer algo anterior
  useEffect(() => {
    const el = scrollRef.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [chat.messages]);

  const send = (text: string) => {
    stickToBottom.current = true;
    void chat.send(text);
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <PageHeader
        title="Buscador"
        description="Respuestas basadas en los documentos oficiales, con cita de la página exacta."
        actions={
          <>
            <HistoryMenu
              tenantId={tenant.tenant_id}
              activeId={chat.conversationId}
              onSelect={(id) => chat.load(id).catch(() => toast.error("No se pudo abrir la consulta."))}
            />
            <Button onClick={chat.reset} disabled={!chat.messages.length}>
              <SquarePen /> <span className="hidden sm:inline">Nueva consulta</span>
            </Button>
          </>
        }
      />

      <div
        ref={scrollRef}
        onScroll={(e) => {
          const el = e.currentTarget;
          stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        }}
        className="min-h-0 flex-1 overflow-y-auto"
      >
        <div className="mx-auto max-w-3xl px-4 py-6 sm:px-6">
          {chat.loadingHistory ? (
            <div className="flex justify-center py-20 text-muted-foreground">
              <Loader2 className="size-5 animate-spin" />
            </div>
          ) : chat.messages.length === 0 ? (
            <ChatEmptyState role={tenant.role} tenantName={tenant.tenant_name} onPick={send} />
          ) : (
            <div className="space-y-8">
              {chat.messages.map((m) =>
                m.role === "user" ? (
                  <div key={m.id} className="flex justify-end">
                    <div className="max-w-[85%] rounded-lg rounded-br-sm bg-accent px-4 py-2.5 text-sm whitespace-pre-wrap text-accent-foreground">
                      {m.content}
                    </div>
                  </div>
                ) : (
                  <AssistantMessage key={m.id} message={m} onRetry={chat.retry} />
                ),
              )}
            </div>
          )}
        </div>
      </div>

      <div className="border-t bg-background">
        <div className="mx-auto max-w-3xl px-4 py-3 sm:px-6">
          <Composer
            busy={chat.busy}
            onSend={send}
            onStop={chat.stop}
            tenantName={tenant.tenant_name}
            autoFocus
          />
        </div>
      </div>
    </div>
  );
}

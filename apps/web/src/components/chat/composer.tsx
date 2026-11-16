"use client";

import { ArrowUp, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";

interface Props {
  busy: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
  tenantName: string;
  autoFocus?: boolean;
}

export function Composer({ busy, onSend, onStop, tenantName, autoFocus }: Props) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  // Altura automática: crece con el texto hasta ~6 líneas
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value]);

  function submit() {
    if (!value.trim() || busy) return;
    onSend(value);
    setValue("");
  }

  return (
    <div>
      <div className="flex items-end gap-2 rounded-lg border bg-card p-2 shadow-xs transition-colors focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/15">
        <textarea
          ref={ref}
          rows={1}
          autoFocus={autoFocus}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
          maxLength={1000}
          placeholder="Escriba su pregunta…"
          aria-label="Pregunta"
          className="max-h-40 min-h-9 flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none placeholder:text-muted-foreground"
        />
        {busy ? (
          <Button size="icon" variant="secondary" onClick={onStop} aria-label="Detener respuesta" className="size-9">
            <Square className="size-3.5 fill-current" />
          </Button>
        ) : (
          <Button size="icon" onClick={submit} disabled={!value.trim()} aria-label="Enviar pregunta" className="size-9">
            <ArrowUp className="size-4" />
          </Button>
        )}
      </div>
      <p className="mt-2 text-center text-xs text-muted-foreground">
        Las respuestas se basan únicamente en los documentos de {tenantName}. Verifique siempre la fuente citada.
        <span className="hidden sm:inline"> · Enter para enviar, Shift + Enter para nueva línea.</span>
      </p>
    </div>
  );
}

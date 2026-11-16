import type { Metadata } from "next";

import { ChatView } from "@/components/chat/chat-view";

export const metadata: Metadata = { title: "Buscador" };

export default function SearchPage() {
  return <ChatView />;
}

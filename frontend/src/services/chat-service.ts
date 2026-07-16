import { apiClient } from "./api-client";
import type { ChatRequest, ChatResponse } from "@/models/chat";

export async function sendChatMessage(payload: ChatRequest) {
  const { data } = await apiClient.post<ChatResponse>("/chat/message", payload);
  return data;
}

export interface KnowledgeCitation {
  source: string;
  section: string;
  score: number;
  excerpt: string;
}

export interface AskResponse {
  query: string;
  answer: string;
  citations: KnowledgeCitation[];
}

/** RAG-backed answer for a common travel question (baggage, airport timing…). */
export async function askKnowledge(query: string): Promise<AskResponse> {
  const { data } = await apiClient.post<AskResponse>("/rag/ask", { query });
  return data;
}

export async function deleteChatSession(sessionId: string) {
  const { data } = await apiClient.delete<{ session_id: string; deleted: boolean }>(
    `/chat/sessions/${sessionId}`,
  );
  return data;
}

import { apiClient } from "./api-client";
import type { ChatRequest, ChatResponse } from "@/models/chat";

export async function sendChatMessage(payload: ChatRequest) {
  const { data } = await apiClient.post<ChatResponse>("/chat/message", payload);
  return data;
}

export async function deleteChatSession(sessionId: string) {
  const { data } = await apiClient.delete<{ session_id: string; deleted: boolean }>(
    `/chat/sessions/${sessionId}`,
  );
  return data;
}

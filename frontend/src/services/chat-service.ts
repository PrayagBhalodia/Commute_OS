import { apiClient } from "./api-client";
import type { ChatRequest, ChatResponse } from "@/models/chat";

export async function sendChatMessage(payload: ChatRequest) {
  const { data } = await apiClient.post<ChatResponse>("/chat/message", payload);
  return data;
}

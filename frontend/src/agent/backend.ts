/** 選擇聊天後端：預設打真的 `/api/chat`（Bedrock）；`VITE_CHAT_BACKEND=mock` 走純前端模擬。 */

import type { ChatModelAdapter } from "@assistant-ui/react";

import { apiCaseAgent } from "./apiAgent";
import { mockCaseAgent } from "./mockAgent";

export type ChatBackend = "api" | "mock";

export const CHAT_BACKEND: ChatBackend = import.meta.env.VITE_CHAT_BACKEND === "mock" ? "mock" : "api";

export const caseAgent: ChatModelAdapter = CHAT_BACKEND === "mock" ? mockCaseAgent : apiCaseAgent;

export const BACKEND_LABEL = CHAT_BACKEND === "mock" ? "前端模擬・不打 API" : "AWS Bedrock";

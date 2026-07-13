import axios, { AxiosError } from "axios";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 45000,
  headers: { "Content-Type": "application/json" },
});

export class ApiClientError extends Error {
  status?: number;
  detail?: unknown;

  constructor(message: string, status?: number, detail?: unknown) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.detail = detail;
  }
}

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ detail?: string }>) => {
    const status = error.response?.status;
    const detail = error.response?.data?.detail ?? error.message;
    const message =
      status === undefined
        ? "Backend offline. Start FastAPI on 127.0.0.1:8000 or use the simulated fallback."
        : typeof detail === "string"
          ? detail
          : `API request failed with status ${status}.`;
    return Promise.reject(new ApiClientError(message, status, detail));
  },
);

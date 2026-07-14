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

type ValidationIssue = { loc?: (string | number)[]; msg?: string };

function formatDetail(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  // FastAPI returns validation errors as an array of {loc, msg} objects.
  if (Array.isArray(detail)) {
    const parts = (detail as ValidationIssue[])
      .map((issue) => {
        const field = issue.loc?.filter((p) => p !== "body").join(".");
        return field ? `${field}: ${issue.msg}` : issue.msg;
      })
      .filter(Boolean);
    if (parts.length) return `Invalid request — ${parts.join("; ")}`;
  }
  return `API request failed with status ${status}.`;
}

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ detail?: unknown }>) => {
    const status = error.response?.status;
    const detail = error.response?.data?.detail ?? error.message;
    const message =
      status === undefined
        ? "Backend offline. Start FastAPI on 127.0.0.1:8000 or use the simulated fallback."
        : formatDetail(detail, status);
    return Promise.reject(new ApiClientError(message, status, detail));
  },
);

const BASE = "";

export interface TaskCreate {
  niche: string;
  region_ids: number[];
  contact?: string;
  masks?: string[];
}

export interface TaskResponse {
  id: string;
  niche: string;
  region_ids: number[];
  region_label: string;
  contact: string | null;
  status: string;
  stage: string | null;
  progress_pct: number;
  error_class: string | null;
  error_message: string | null;
  suggested_niche?: string | null;
  search_masks?: string[] | null;
  download_url: string | null;
  source: string;
  created_at: string;
  updated_at: string;
}

export interface ProgressResponse {
  stage: string | null;
  step: number;
  total_steps: number;
  percent: number;
  label: string;
  terminal: boolean;
  needs_manual: boolean;
}

export interface Region {
  id: number;
  name: string;
}

export interface AdminStats {
  total: number;
  done: number;
  failed: number;
  awaiting_manual: number;
  median_seconds: number;
  p95_seconds: number;
  success_rate_pct: number;
  by_status: Record<string, number>;
}

export type AdminEvent = Record<string, unknown>;

export class ApiError extends Error {
  status: number;
  payload: unknown;

  constructor(status: number, message: string, payload?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

export class AdminAuthError extends ApiError {
  constructor(message = "Требуется вход в админ-панель") {
    super(401, message);
    this.name = "AdminAuthError";
  }
}

type RequestOptions = RequestInit & {
  admin?: boolean;
};

function extractErrorMessage(payload: unknown, fallback: string) {
  if (typeof payload === "string" && payload.trim()) {
    return payload;
  }

  if (payload && typeof payload === "object") {
    const record = payload as Record<string, unknown>;
    const detail = record.detail ?? record.message ?? record.error;

    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
  }

  return fallback;
}

async function parseResponse(response: Response) {
  if (response.status === 204) {
    return undefined;
  }

  const contentType = response.headers.get("content-type") ?? "";

  if (contentType.includes("application/json")) {
    return response.json();
  }

  return response.text();
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { admin, headers, ...init } = options;
  const response = await fetch(`${BASE}${path}`, {
    credentials: "same-origin",
    ...init,
    headers,
  });

  const payload = await parseResponse(response);

  if (!response.ok) {
    if (admin && response.status === 401) {
      throw new AdminAuthError();
    }

    throw new ApiError(
      response.status,
      extractErrorMessage(payload, "Не удалось выполнить запрос"),
      payload,
    );
  }

  return payload as T;
}

function jsonHeaders() {
  return {
    "Content-Type": "application/json",
  };
}

export async function createTask(
  data: TaskCreate,
): Promise<{ task_id: string; status: string }> {
  return request("/api/tasks", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
}

export async function getTask(taskId: string): Promise<TaskResponse> {
  return request(`/api/tasks/${encodeURIComponent(taskId)}`);
}

export async function getProgress(taskId: string): Promise<ProgressResponse> {
  return request(`/api/tasks/${encodeURIComponent(taskId)}/progress`);
}

export async function getRegions(query = ""): Promise<Region[]> {
  const params = new URLSearchParams();

  if (query.trim()) {
    params.set("q", query.trim());
  }

  const suffix = params.toString() ? `?${params.toString()}` : "";
  return request(`/api/regions${suffix}`);
}

export async function generateMasks(niche: string): Promise<{ masks: string[] }> {
  return request("/api/masks", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ niche }),
  });
}

export async function adminLogin(password: string): Promise<void> {
  await request<void>("/access/login", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ password }),
  });
}

export async function adminLogout(): Promise<void> {
  await request<void>("/access/logout", {
    method: "POST",
    admin: true,
  });
}

export async function getAdminTasks(
  params: { status?: string; limit?: number; offset?: number } = {},
): Promise<{ items: TaskResponse[]; total: number }> {
  const query = new URLSearchParams();

  if (params.status) {
    query.set("status", params.status);
  }

  if (typeof params.limit === "number") {
    query.set("limit", String(params.limit));
  }

  if (typeof params.offset === "number") {
    query.set("offset", String(params.offset));
  }

  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request(`/api/admin/tasks${suffix}`, { admin: true });
}

export async function getAdminTask(
  taskId: string,
): Promise<{ task: TaskResponse; events: AdminEvent[] }> {
  return request(`/api/admin/tasks/${encodeURIComponent(taskId)}`, {
    admin: true,
  });
}

export async function retryTask(taskId: string): Promise<void> {
  await request<void>(`/api/admin/tasks/${encodeURIComponent(taskId)}/retry`, {
    method: "POST",
    admin: true,
  });
}

export async function cancelTask(taskId: string): Promise<void> {
  await request<void>(`/api/admin/tasks/${encodeURIComponent(taskId)}/cancel`, {
    method: "POST",
    admin: true,
  });
}

export async function uploadXls(
  taskId: string,
  file: File,
): Promise<{ parsed_rows: number }> {
  const formData = new FormData();
  formData.append("file", file);

  return request(`/api/admin/tasks/${encodeURIComponent(taskId)}/upload-xls`, {
    method: "POST",
    body: formData,
    admin: true,
  });
}

export async function getAdminStats(): Promise<AdminStats> {
  return request("/api/admin/stats", { admin: true });
}

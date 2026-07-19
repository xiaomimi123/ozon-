import { api } from "./client";
export const listAccounts = (platform?: string) =>
  api.get("/accounts", { params: platform ? { platform } : {} }).then((r) => r.data);
export const createAccount = (body: { platform: string; label?: string; credentials: any; daily_limit?: number; min_interval_sec?: number }) =>
  api.post("/accounts", body).then((r) => r.data);
export const updateAccount = (id: number, body: any) => api.put(`/accounts/${id}`, body).then((r) => r.data);
export const deleteAccount = (id: number) => api.delete(`/accounts/${id}`).then((r) => r.data);

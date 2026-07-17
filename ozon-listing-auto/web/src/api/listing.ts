import { api } from "./client";
export const buildDrafts = (taskId: number, shopId?: number) =>
  api.post(`/listing/build?task_id=${taskId}${shopId ? `&shop_id=${shopId}` : ""}`).then(r => r.data);
export const getDrafts = (taskId: number, status?: string) =>
  api.get(`/listing/drafts?task_id=${taskId}${status ? `&status=${status}` : ""}`).then(r => r.data);
export const confirmDraft = (draftId: number) => api.post(`/listing/${draftId}/confirm`).then(r => r.data);
export const autoConfirm = (taskId: number) => api.post(`/listing/auto-confirm?task_id=${taskId}`).then(r => r.data);
export const publishDrafts = (taskId: number) => api.post(`/listing/publish?task_id=${taskId}&sync=true`).then(r => r.data);

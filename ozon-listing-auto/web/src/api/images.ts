import { api } from "./client";

export const processImages = (taskId: number) =>
  api.post(`/images/process?task_id=${taskId}&sync=true`).then(r => r.data);
export const listImages = (taskId: number, status?: string) =>
  api.get(`/images?task_id=${taskId}${status ? `&status=${status}` : ""}`).then(r => r.data);
export const approveImage = (id: number) => api.post(`/images/${id}/approve`).then(r => r.data);
export const rejectImage = (id: number) => api.post(`/images/${id}/reject`).then(r => r.data);

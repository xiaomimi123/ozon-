import { api } from "./client";

export const startScore = (taskId: number) => api.post(`/score/start?task_id=${taskId}&sync=true`).then(r => r.data);
export const getQueue = (taskId: number) => api.get(`/review/queue?task_id=${taskId}`).then(r => r.data);
export const decide = (candidateId: number, decision: "adopt" | "reject", note?: string) =>
  api.post(`/review/${candidateId}`, { decision, note }).then(r => r.data);
export const autoAdopt = (taskId: number) => api.post(`/review/auto-adopt?task_id=${taskId}`).then(r => r.data);

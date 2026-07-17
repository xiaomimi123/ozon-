import { api } from "./client";
export const schedule = (taskId: number) => api.post(`/publish/schedule?task_id=${taskId}`).then(r => r.data);
export const tick = (taskId: number) => api.post(`/publish/tick?task_id=${taskId}&sync=true`).then(r => r.data);
export const getMonitor = (taskId: number) => api.get(`/publish/monitor?task_id=${taskId}`).then(r => r.data);

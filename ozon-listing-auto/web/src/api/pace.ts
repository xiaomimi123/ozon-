import { api } from "./client";
export interface Pace { min_interval_sec: number; max_interval_sec: number; daily_limit: number; active_hours: number[]; wait_ozon_approval: boolean; }
export const getPace = (taskId: number) => api.get(`/pace?task_id=${taskId}`).then(r => r.data);
export const savePace = (taskId: number, body: Pace) => api.put(`/pace?task_id=${taskId}`, body).then(r => r.data);

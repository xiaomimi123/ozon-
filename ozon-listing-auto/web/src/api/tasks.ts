import { api } from "./client";

export interface TaskBody {
  name: string; listing_mode: string; entry_type: string; entry_value: string;
  provider: string; source_platforms: string[]; review_config?: Record<string, unknown>;
}
export const createTask = (b: TaskBody) => api.post("/tasks", b).then(r => r.data);
export const listTasks = () => api.get("/tasks").then(r => r.data);
export const startCollect = (id: number) => api.post(`/collect/start?task_id=${id}&sync=true`).then(r => r.data);
export const pauseCollect = (id: number) => api.post(`/collect/pause?task_id=${id}`).then(r => r.data);

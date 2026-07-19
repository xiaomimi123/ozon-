import { api } from "./client";

export const listUsers = () => api.get("/users").then((r) => r.data);
export const createUser = (b: { username: string; password: string; role: string }) =>
  api.post("/users", b).then((r) => r.data);
export const updateUser = (id: number, b: { role?: string; is_active?: boolean }) =>
  api.put(`/users/${id}`, b).then((r) => r.data);
export const resetPassword = (id: number, password: string) =>
  api.post(`/users/${id}/password`, { password }).then((r) => r.data);
export const deleteUser = (id: number) => api.delete(`/users/${id}`).then((r) => r.data);

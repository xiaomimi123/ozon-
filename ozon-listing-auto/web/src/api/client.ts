import axios from "axios";
import { auth } from "../store/auth";

export const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE || "/api" });
api.interceptors.request.use((cfg) => {
  const t = auth.token;
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});
export async function login(username: string, password: string) {
  const form = new URLSearchParams({ username, password });
  const { data } = await api.post("/auth/login", form, { headers: { "Content-Type": "application/x-www-form-urlencoded" } });
  auth.set(data.access_token, data.role);
  return data;
}

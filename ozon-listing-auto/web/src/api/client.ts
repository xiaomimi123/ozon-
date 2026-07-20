import axios from "axios";
import { message } from "antd";
import { auth } from "../store/auth";

export const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE || "/api" });
api.interceptors.request.use((cfg) => {
  const t = auth.token;
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});
// 登录会话过期(401)：清登录态 + 提示 + 跳登录页；登录接口自身的 401 交给登录页处理。
api.interceptors.response.use(
  (r) => r,
  (err) => {
    const url = err?.config?.url || "";
    if (err?.response?.status === 401 && !url.includes("/auth/login")) {
      auth.clear();
      if (!window.location.pathname.endsWith("/login")) {
        message.warning("登录已过期，请重新登录");
        window.location.href = "/login";
      }
    }
    return Promise.reject(err);
  }
);
export async function login(username: string, password: string) {
  const form = new URLSearchParams({ username, password });
  const { data } = await api.post("/auth/login", form, { headers: { "Content-Type": "application/x-www-form-urlencoded" } });
  auth.set(data.access_token, data.role);
  return data;
}

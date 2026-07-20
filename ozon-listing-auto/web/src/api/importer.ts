import { api } from "./client";
export const listImported = (platform?: string) =>
  api.get("/import/offers", { params: platform ? { platform } : {} }).then((r) => r.data);
export const listCaptures = () => api.get("/import/captures").then((r) => r.data);
export const getCapture = (id: number) => api.get(`/import/captures/${id}`).then((r) => r.data);

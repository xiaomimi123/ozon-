import { api } from "./client";
export const listShops = () => api.get("/shops").then(r => r.data);
export const createShop = (body: { name: string; client_id: string; api_key: string; is_sandbox: boolean }) =>
  api.post("/shops", body).then(r => r.data);
export const deleteShop = (id: number) => api.delete(`/shops/${id}`).then(r => r.data);

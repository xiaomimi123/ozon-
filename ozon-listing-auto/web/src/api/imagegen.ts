import { api } from "./client";

export const getImagegen = () => api.get("/settings/imagegen").then(r => r.data);
export const putImagegen = (body: any) => api.put("/settings/imagegen", body).then(r => r.data);

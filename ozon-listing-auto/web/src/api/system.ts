import { api } from "./client";

export const getSystem = () => api.get("/settings/system").then(r => r.data);
export const putSystem = (body: any) => api.put("/settings/system", body).then(r => r.data);

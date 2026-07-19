import { api } from "./client";

export const getSources = () => api.get("/settings/sources").then(r => r.data);
export const putSources = (body: any) => api.put("/settings/sources", body).then(r => r.data);

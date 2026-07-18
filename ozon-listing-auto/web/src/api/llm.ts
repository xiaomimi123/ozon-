import { api } from "./client";

export const getLlm = () => api.get("/settings/llm").then(r => r.data);
export const putLlm = (body: any) => api.put("/settings/llm", body).then(r => r.data);

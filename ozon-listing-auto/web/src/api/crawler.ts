import { api } from "./client";

export const getCrawler = () => api.get("/settings/crawler").then(r => r.data);
export const putCrawler = (body: any) => api.put("/settings/crawler", body).then(r => r.data);

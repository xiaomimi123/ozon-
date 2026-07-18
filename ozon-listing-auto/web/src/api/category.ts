import { api } from "./client";

export const getCategories = (parentId?: number) =>
  api.get(`/categories${parentId != null ? `?parent_id=${parentId}` : ""}`).then(r => r.data);
export const suggestCategory = (candidateId: number) =>
  api.post(`/category/suggest?candidate_id=${candidateId}`).then(r => r.data);
export const confirmCategory = (draftId: number, body: any) =>
  api.post(`/listing/${draftId}/confirm-category`, body).then(r => r.data);

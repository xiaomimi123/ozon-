import { api } from "./client";
export const getTypes = () => api.get("/ozon-catalog/types").then(r => r.data);
export const getAttributes = (category_id: number, type_id: number) =>
  api.get("/ozon-catalog/attributes", { params: { category_id, type_id } }).then(r => r.data);
export const getAttributeValues = (category_id: number, type_id: number, attribute_id: number) =>
  api.get("/ozon-catalog/attribute-values", { params: { category_id, type_id, attribute_id } }).then(r => r.data);
export const confirmCreateFields = (draftId: number, body: any) =>
  api.post(`/listing/${draftId}/confirm-create-fields`, body).then(r => r.data);

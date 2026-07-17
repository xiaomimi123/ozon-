import { api } from "./client";

export interface ProductFilter {
  sales_min?: number; return_rate_max?: number; rating_min?: number;
  weight_min?: number; weight_max?: number; follow_min?: number; follow_max?: number; keyword?: string;
  listed_after?: string;
}
export function listProducts(taskId: number, f: ProductFilter, page = 1, pageSize = 20) {
  const params: any = { task_id: taskId, page, page_size: pageSize };
  Object.entries(f).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") params[k] = v; });
  return api.get("/products", { params }).then(r => r.data);
}

import { api } from "./client";

export interface PricingParams {
  mode: string;
  commission_rate: number;
  fulfillment_rate: number;
  fx: number;
  target_margin: number;
  logistics: number;
  min_price: number;
  strike_coeff: number;
  formula?: string;
}

export const savePricing = (params: PricingParams) => api.put("/settings/pricing", params).then(r => r.data);

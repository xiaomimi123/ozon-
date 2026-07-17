const TOKEN_KEY = "ozon_token";
const ROLE_KEY = "ozon_role";
export const auth = {
  get token() { return localStorage.getItem(TOKEN_KEY); },
  get role() { return localStorage.getItem(ROLE_KEY); },
  set(token: string, role: string) { localStorage.setItem(TOKEN_KEY, token); localStorage.setItem(ROLE_KEY, role); },
  clear() { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(ROLE_KEY); },
};

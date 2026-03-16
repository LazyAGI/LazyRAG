/**
 * Minimal auth for LazyRAG: getUserInfo from storage, logout redirect to /login.
 * Compatible with AuthServiceApi login (token stored after username/password login).
 */
const STORAGE_KEY = "lazyrag:user";

export interface UserInfo {
  token: string;
  username: string;
  userId?: string;
  role?: string;
  email?: string;
  displayName?: string;
  phone?: string;
  clientId?: string;
  loginType?: string;
  idToken?: string;
  refreshToken?: string;
  timestamp?: number;
}

function getStored(): UserInfo | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as UserInfo;
  } catch {
    return null;
  }
}

export const AgentAppsAuth = {
  getUserInfo(): UserInfo | null {
    return getStored();
  },

  getAccessToken(): string {
    return getStored()?.token || "";
  },

  isLoggedIn(): boolean {
    return Boolean(getStored()?.token);
  },

  clearUserInfo() {
    localStorage.removeItem(STORAGE_KEY);
  },

  getAuthHeaders(): Record<string, string> {
    const token = this.getAccessToken();
    return token ? { authorization: `Bearer ${token}` } : {};
  },

  getLoginUrl(): string {
    return `${window.location.origin}${window.location.pathname || ""}#/login`;
  },

  logout(redirectUrl?: string) {
    this.clearUserInfo();
    const target = redirectUrl || this.getLoginUrl();
    window.location.href = target;
  },

  setUserInfo(info: UserInfo) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(info));
  },

  updateUserInfo(patch: Partial<UserInfo>) {
    const current = getStored();
    if (!current) return;
    this.setUserInfo({
      ...current,
      ...patch,
    });
  },
};

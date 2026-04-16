import { AgentAppsAuth } from "@/components/auth";
import { BASE_URL } from "@/components/request";
import i18n from "@/i18n";


const API_BASE = `${BASE_URL || window.location.origin}/api/authservice/v1`;
const RESULT_STORAGE_KEY = "lazyrag:datasource:feishu-oauth:result";
const DRAFT_STORAGE_KEY = "lazyrag:datasource:feishu-oauth:draft";

export const FEISHU_DATA_SOURCE_OAUTH_CHANNEL =
  "lazyrag:datasource:feishu-oauth";

export type FeishuConnectionStatus =
  | "pending"
  | "connected"
  | "expired"
  | "error";

export interface FeishuDataSourceConnection {
  provider: "feishu";
  connectionId: string;
  status: FeishuConnectionStatus;
  accountName: string;
  grantedScopes: string[];
  connectedAt?: string;
  expiresAt?: string;
  refreshExpiresAt?: string;
  tenantKey?: string;
  openId?: string;
  unionId?: string;
  avatarUrl?: string;
  accessTokenMasked?: string;
  refreshTokenMasked?: string;
}

export interface FeishuDataSourceWizardDraft {
  wizardOpen: boolean;
  wizardStep: number;
  wizardMode: "create" | "edit";
  selectedType: string | null;
  editingId: string | null;
  oauthState: string;
  connectionVerified: boolean;
  oauthConnection: FeishuDataSourceConnection | null;
  formValues: Record<string, unknown>;
}

export type FeishuDataSourceOAuthMessage =
  | {
      channel: typeof FEISHU_DATA_SOURCE_OAUTH_CHANNEL;
      source: "feishu-data-source";
      status: "success";
      connection: FeishuDataSourceConnection;
    }
  | {
      channel: typeof FEISHU_DATA_SOURCE_OAUTH_CHANNEL;
      source: "feishu-data-source";
      status: "error";
      message: string;
    };

function getBaseName() {
  return ((window as Window & { BASENAME?: string }).BASENAME || "").trim();
}

function getAuthHeaders() {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  const token = AgentAppsAuth.getAccessToken();
  const userInfo = AgentAppsAuth.getUserInfo();

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  if (userInfo?.userId) {
    headers["X-User-Id"] = userInfo.userId;
  }

  return headers;
}

function parseJsonResponse(response: Response) {
  return response.json().catch(() => ({}));
}

function unwrapPayload<T>(payload: any): T {
  return (payload?.data || payload) as T;
}

function getErrorMessage(payload: any, fallback: string) {
  if (typeof payload?.message === "string" && payload.message.trim()) {
    return payload.message;
  }

  if (typeof payload?.detail === "string" && payload.detail.trim()) {
    return payload.detail;
  }

  if (Array.isArray(payload?.detail)) {
    const joined = payload.detail
      .map((item: any) =>
        typeof item === "string" ? item : item?.msg || item?.message,
      )
      .filter(Boolean)
      .join("；");

    if (joined) {
      return joined;
    }
  }

  return fallback;
}

function normalizeScopes(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => (typeof item === "string" ? item.trim() : ""))
      .filter(Boolean);
  }

  if (typeof value === "string") {
    return value
      .split(/[,\s]+/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  return [];
}

function normalizeStatus(value: unknown): FeishuConnectionStatus {
  if (value === "connected" || value === "expired" || value === "error") {
    return value;
  }
  return "pending";
}

function maskToken(token?: string) {
  if (!token) {
    return undefined;
  }

  if (token.length <= 12) {
    return `${token.slice(0, 3)}***${token.slice(-3)}`;
  }

  return `${token.slice(0, 6)}...${token.slice(-4)}`;
}

function normalizeConnection(payload: any): FeishuDataSourceConnection {
  const raw = unwrapPayload<any>(payload);
  const connection = raw?.connection || raw?.oauth_connection || raw;
  const accessToken = connection?.access_token || raw?.access_token;
  const refreshToken = connection?.refresh_token || raw?.refresh_token;

  return {
    provider: "feishu",
    connectionId: String(
      connection?.connection_id ||
        connection?.id ||
        connection?.open_id ||
        raw?.connection_id ||
        `feishu-${Date.now()}`,
    ),
    status: normalizeStatus(connection?.status || raw?.status || "connected"),
    accountName:
      connection?.account_name ||
      connection?.accountName ||
      connection?.name ||
      connection?.display_name ||
      connection?.tenant_name ||
      i18n.t("admin.dataSourceFeishuConnectedAccountFallback"),
    grantedScopes: normalizeScopes(
      connection?.granted_scopes ||
        connection?.scope ||
        connection?.scopes ||
        raw?.granted_scopes ||
        raw?.scope ||
        raw?.scopes,
    ),
    connectedAt: connection?.connected_at || raw?.connected_at,
    expiresAt: connection?.expires_at || raw?.expires_at,
    refreshExpiresAt:
      connection?.refresh_expires_at || raw?.refresh_expires_at,
    tenantKey: connection?.tenant_key || raw?.tenant_key,
    openId: connection?.open_id || raw?.open_id,
    unionId: connection?.union_id || raw?.union_id,
    avatarUrl: connection?.avatar_url || raw?.avatar_url,
    accessTokenMasked:
      connection?.access_token_masked ||
      raw?.access_token_masked ||
      maskToken(accessToken),
    refreshTokenMasked:
      connection?.refresh_token_masked ||
      raw?.refresh_token_masked ||
      maskToken(refreshToken),
  };
}

export function getFeishuDataSourceCallbackUrl() {
  return `${window.location.origin}${getBaseName()}/oauth/feishu/data-source/callback`;
}

export function getDataSourceManagementUrl() {
  return `${window.location.origin}${getBaseName()}/admin/data-sources`;
}

export function openCenteredPopup(url: string, title: string) {
  const width = 560;
  const height = 760;
  const dualScreenLeft =
    window.screenLeft !== undefined ? window.screenLeft : window.screenX;
  const dualScreenTop =
    window.screenTop !== undefined ? window.screenTop : window.screenY;
  const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
  const viewportHeight =
    window.innerHeight || document.documentElement.clientHeight;
  const left = Math.max(0, dualScreenLeft + (viewportWidth - width) / 2);
  const top = Math.max(0, dualScreenTop + (viewportHeight - height) / 2);

  return window.open(
    url,
    title,
    [
      `width=${width}`,
      `height=${height}`,
      `left=${Math.round(left)}`,
      `top=${Math.round(top)}`,
      "resizable=yes",
      "scrollbars=yes",
    ].join(","),
  );
}

export async function requestFeishuDataSourceAuthorizeUrl(input: {
  scopes: string[];
  target?: string;
  sourceId?: string | null;
  reconnect?: boolean;
}) {
  const params = new URLSearchParams();
  params.set("scene", "data_source");
  params.set("redirect_uri", getFeishuDataSourceCallbackUrl());

  if (input.scopes.length > 0) {
    params.set("scopes", input.scopes.join(","));
  }
  if (input.target?.trim()) {
    params.set("target", input.target.trim());
  }
  if (input.sourceId) {
    params.set("source_id", input.sourceId);
  }
  if (input.reconnect) {
    params.set("reconnect", "1");
  }

  const response = await fetch(
    `${API_BASE}/auth/feishu/authorize-url?${params.toString()}`,
    {
      credentials: "include",
      headers: getAuthHeaders(),
    },
  );
  const payload = await parseJsonResponse(response);
  const data = unwrapPayload<any>(payload);
  const authorizeUrl = data?.authorize_url || data?.authorizeUrl;

  if (!response.ok || typeof authorizeUrl !== "string" || !authorizeUrl.trim()) {
    throw new Error(getErrorMessage(payload, i18n.t("admin.dataSourceAuthorizeUrlFailed")));
  }

  return authorizeUrl;
}

export async function finishFeishuDataSourceOAuth(code: string, state: string) {
  const response = await fetch(`${API_BASE}/auth/feishu/callback`, {
    method: "POST",
    credentials: "include",
    headers: getAuthHeaders(),
    body: JSON.stringify({
      code,
      state,
      scene: "data_source",
      redirect_uri: getFeishuDataSourceCallbackUrl(),
    }),
  });
  const payload = await parseJsonResponse(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(payload, i18n.t("admin.dataSourceOauthFailedRetry")));
  }

  return normalizeConnection(payload);
}

export function saveFeishuDataSourceOAuthResult(
  payload: FeishuDataSourceOAuthMessage,
) {
  sessionStorage.setItem(RESULT_STORAGE_KEY, JSON.stringify(payload));
}

export function consumeFeishuDataSourceOAuthResult() {
  const raw = sessionStorage.getItem(RESULT_STORAGE_KEY);
  if (!raw) {
    return null;
  }

  sessionStorage.removeItem(RESULT_STORAGE_KEY);

  try {
    return JSON.parse(raw) as FeishuDataSourceOAuthMessage;
  } catch {
    return null;
  }
}

export function saveFeishuDataSourceWizardDraft(
  payload: FeishuDataSourceWizardDraft,
) {
  sessionStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(payload));
}

export function consumeFeishuDataSourceWizardDraft() {
  const raw = sessionStorage.getItem(DRAFT_STORAGE_KEY);
  if (!raw) {
    return null;
  }

  sessionStorage.removeItem(DRAFT_STORAGE_KEY);

  try {
    return JSON.parse(raw) as FeishuDataSourceWizardDraft;
  } catch {
    return null;
  }
}

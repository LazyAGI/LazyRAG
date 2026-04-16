import { BASE_URL } from "@/components/request";
import {
  storeLoginSession,
  unwrapLoginResponse,
} from "@/modules/signin/utils/request";


const authServiceBase = `${BASE_URL || window.location.origin}/api/authservice/v1`;


async function parseJsonResponse(response: Response) {
  return response.json().catch(() => ({}));
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


export async function startFeishuLogin() {
  const response = await fetch(`${authServiceBase}/auth/feishu/authorize-url`, {
    credentials: "include",
  });
  const payload = await parseJsonResponse(response);

  if (!response.ok || !payload?.authorize_url) {
    throw new Error(getErrorMessage(payload, "获取飞书授权地址失败"));
  }

  window.location.href = payload.authorize_url;
}


export async function finishFeishuLogin(code: string, state: string) {
  const response = await fetch(`${authServiceBase}/auth/feishu/callback`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ code, state }),
  });
  const payload = await parseJsonResponse(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(payload, "飞书登录失败"));
  }

  const loginData = unwrapLoginResponse(payload?.data || payload);
  await storeLoginSession(loginData, "feishu");
  return loginData;
}

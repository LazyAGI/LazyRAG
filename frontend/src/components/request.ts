import axios from "axios";
import type { AxiosInstance } from "axios";
import { message } from "antd";
import { AgentAppsAuth } from "@/components/auth";

export const BASE_URL =
  (typeof import.meta !== "undefined" &&
    (import.meta as any).env?.VITE_API_BASE_URL) ||
  (typeof window !== "undefined" && window.location.origin) ||
  "";

const axiosInstance: AxiosInstance = axios.create({
  timeout: 30000,
});

function applyOptionalAuthHeader(config: any) {
  const token = AgentAppsAuth.getAccessToken();
  config.headers = config.headers ?? {};

  if (token) {
    if (!config.headers.Authorization && !config.headers.authorization) {
      config.headers.authorization = `Bearer ${token}`;
    }
    return config;
  }

  if (config.headers.Authorization === "Bearer undefined") {
    delete config.headers.Authorization;
  }
  if (config.headers.authorization === "Bearer undefined") {
    delete config.headers.authorization;
  }
  return config;
}

function isCanceledError(error: any): boolean {
  if (error?.code === "ERR_CANCELED" || error?.name === "CanceledError")
    return true;
  if (error?.config?.signal?.aborted) return true;
  const msg = (error?.message || "").toLowerCase();
  return (
    msg.includes("canceled") ||
    msg.includes("cancelled") ||
    msg.includes("aborted")
  );
}

function extractErrorMessage(error: any): string | undefined {
  const responseData = error?.response?.data;
  const detail = responseData?.detail;

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item: any) =>
        typeof item === "string" ? item : item?.msg || item?.message,
      )
      .filter(Boolean);

    if (messages.length > 0) {
      return messages.join("；");
    }
  }

  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }

  if (
    typeof responseData?.message === "string" &&
    responseData.message.trim()
  ) {
    return responseData.message;
  }

  if (
    typeof error?.response?.message === "string" &&
    error.response.message.trim()
  ) {
    return error.response.message;
  }

  if (typeof error?.message === "string" && error.message.trim()) {
    return error.message;
  }

  return undefined;
}

export const handleError = async (error: any) => {
  if (isCanceledError(error)) return Promise.reject(error);
  if (error.response) {
    if (error.response.status === 403) {
      const errMsg = extractErrorMessage(error);
      if (errMsg === "User is disabled") {
        message.error("用户被禁用");
        await AgentAppsAuth.logout(
          `${BASE_URL || window.location.origin}/#/agent/chat`,
        );
        return;
      }
      message.error(errMsg || "访问被拒绝");
    } else if (error.response.status === 401) {
      if (AgentAppsAuth.isLoggedIn()) {
        message.warning(
          extractErrorMessage(error) || "登录状态已失效，即将跳转到登录页",
        );
        AgentAppsAuth.logout();
        return;
      }
      AgentAppsAuth.logout();
      return;
    } else {
      message.error(extractErrorMessage(error) || "请求失败");
    }
  } else if (error.request) {
    message.error("服务器无响应");
  } else {
    message.error(error.message || "请求发生错误");
  }
  return Promise.reject(error);
};

axiosInstance.interceptors.request.use(
  (config) => applyOptionalAuthHeader(config),
  handleError,
);
axiosInstance.interceptors.response.use((response) => response, handleError);

export { axiosInstance };

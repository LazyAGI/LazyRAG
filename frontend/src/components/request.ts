import axios from "axios";
import type { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from "axios";
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

let isRefreshing = false;
let refreshQueue: Array<(token: string) => void> = [];

function processQueue(newToken: string) {
  refreshQueue.forEach((cb) => cb(newToken));
  refreshQueue = [];
}

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

function isRefreshEndpoint(url?: string): boolean {
  if (!url) return false;
  return url.includes("/auth/refresh") || url.includes("/auth/login") || url.includes("/auth/logout");
}

export const handleError = async (error: AxiosError) => {
  if (isCanceledError(error)) return Promise.reject(error);
  
  const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
  
  if (error.response) {
    if (error.response.status === 403) {
      const errMsg = extractErrorMessage(error);
      if (errMsg === "User is disabled") {
        message.error("用户被禁用");
        void AgentAppsAuth.logout(
          `${BASE_URL || window.location.origin}/#/agent/chat`,
        );
        return Promise.reject(error);
      }
      message.error(errMsg || "访问被拒绝");
    } else if (error.response.status === 401) {
      if (isRefreshEndpoint(originalRequest?.url)) {
        if (AgentAppsAuth.isLoggedIn()) {
          message.warning("登录状态已失效，请重新登录");
        }
        void AgentAppsAuth.logout();
        return Promise.reject(error);
      }

      if (!originalRequest || originalRequest._retry) {
        if (AgentAppsAuth.isLoggedIn()) {
          message.warning("认证失败，请重新登录");
        }
        void AgentAppsAuth.logout();
        return Promise.reject(error);
      }

      originalRequest._retry = true;

      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          refreshQueue.push((newToken: string) => {
            if (originalRequest.headers) {
              originalRequest.headers.authorization = `Bearer ${newToken}`;
            }
            axiosInstance(originalRequest).then(resolve).catch(reject);
          });
        });
      }

      isRefreshing = true;

      try {
        const newAccessToken = await AgentAppsAuth.refreshAccessToken();
        
        processQueue(newAccessToken);

        if (originalRequest.headers) {
          originalRequest.headers.authorization = `Bearer ${newAccessToken}`;
        }

        return await axiosInstance(originalRequest);
      } catch (refreshError) {
        console.error("Token refresh failed:", refreshError);
        
        refreshQueue.forEach((cb) => {
          cb("");
        });
        refreshQueue = [];
        
        message.warning("登录状态已失效，请重新登录");
        void AgentAppsAuth.logout();
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
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

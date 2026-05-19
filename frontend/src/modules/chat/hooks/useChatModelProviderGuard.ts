import { useCallback, useEffect, useRef, useState } from "react";
import { axiosInstance, BASE_URL } from "@/components/request";

type ApiEnvelope<T> = {
  data?: T;
};

interface SelectedModelItem {
  model_id?: string;
  model_type?: string;
}

interface SelectedModelsResponse {
  selections?: SelectedModelItem[];
}

export type ChatModelProviderStatus =
  | "idle"
  | "loading"
  | "ready"
  | "missing"
  | "error";

const chatModelTypes = new Set(["llm-chat", "llm"]);

function unwrapResponse<T>(payload: ApiEnvelope<T> | T): T {
  if (payload && typeof payload === "object" && "data" in payload) {
    return (payload as ApiEnvelope<T>).data as T;
  }
  return payload as T;
}

function hasChatModel(selections?: SelectedModelItem[]) {
  return (selections || []).some((selection) => {
    const modelType = (selection.model_type || "").trim().toLowerCase();
    return chatModelTypes.has(modelType) && Boolean(selection.model_id?.trim());
  });
}

export function useChatModelProviderGuard() {
  const [status, setStatus] = useState<ChatModelProviderStatus>("idle");
  const requestIdRef = useRef(0);
  const mountedRef = useRef(true);

  const refresh = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setStatus("loading");

    try {
      const response = await axiosInstance.get<
        ApiEnvelope<SelectedModelsResponse> | SelectedModelsResponse
      >(`${BASE_URL}/api/core/model_providers/selected_models`);
      const data = unwrapResponse<SelectedModelsResponse>(response.data);
      if (!mountedRef.current || requestIdRef.current !== requestId) {
        return false;
      }
      const ready = hasChatModel(data.selections);
      setStatus(ready ? "ready" : "missing");
      return ready;
    } catch {
      if (mountedRef.current && requestIdRef.current === requestId) {
        setStatus("error");
      }
      return false;
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    void refresh();

    return () => {
      mountedRef.current = false;
    };
  }, [refresh]);

  return {
    canChat: status === "ready",
    isChecking: status === "idle" || status === "loading",
    needsModelProviderConfig: status === "missing",
    refresh,
    status,
  };
}

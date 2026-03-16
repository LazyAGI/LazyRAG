import { create } from "zustand";

/** 模型选择类型：LazyRAG | DeepSeek | 双模比较 */
export type ModelSelectionType = "value_engineering" | "deepseek" | "both";

/** 模型选择文案 */
export const MODEL_LABELS: Record<ModelSelectionType, string> = {
  value_engineering: "LazyRAG",
  deepseek: "DeepSeek",
  both: "双模比较",
};

/** 模型选项 */
export const MODEL_OPTIONS = [
  {
    value: "value_engineering" as const,
    label: "LazyRAG 大模型",
    description: "LazyRAG 多模态大模型",
  },
  {
    value: "deepseek" as const,
    label: "DeepSeek",
    description: "通用领域文本大模型",
  },
] as const;

const DEFAULT_MODEL: ModelSelectionType = "value_engineering";

/**
 * 从后端返回的 models 数组解析模型选择类型
 * @param models 后端返回的 conversation.models 数组，如 ["LazyRAG 大模型"] 或 ["LazyRAG 大模型", "DeepSeek"]
 * @returns 模型选择类型
 */
export function parseModelSelectionFromModels(
  models?: string[],
): ModelSelectionType {
  if (!models || models.length === 0) {
    return DEFAULT_MODEL;
  }

  const hasValueEngineering = models.some(
    (m) =>
      m === MODEL_OPTIONS[0].label ||
      m === "LazyRAG 大模型" ||
      m === "lazyRag 大模型",
  );
  const hasDeepSeek = models.some(
    (m) => m === MODEL_OPTIONS[1].label || m === "DeepSeek",
  );

  if (hasValueEngineering && hasDeepSeek) {
    return "both";
  } else if (hasDeepSeek) {
    return "deepseek";
  } else {
    return "value_engineering";
  }
}

interface ModelSelectionStore {
  /** 每个会话的模型选择，key 为 conversationId，空字符串表示新对话 */
  conversationModelSelection: Record<string, ModelSelectionType>;
  /** 获取指定会话的模型选择，默认 value_engineering */
  getModelSelection: (conversationId: string) => ModelSelectionType;
  /** 设置指定会话的模型选择 */
  setModelSelection: (
    conversationId: string,
    selection: ModelSelectionType,
  ) => void;
  /** 重置新对话的模型选择为默认 */
  resetForNewChat: () => void;
  /** 清除指定会话的模型选择 */
  clearModelSelection: (conversationId: string) => void;
}

export const useModelSelectionStore = create<ModelSelectionStore>()(
  (set, get) => ({
    conversationModelSelection: {},
    getModelSelection: (conversationId: string) => {
      const selection = get().conversationModelSelection[conversationId];
      return selection ?? DEFAULT_MODEL;
    },
    setModelSelection: (
      conversationId: string,
      selection: ModelSelectionType,
    ) => {
      set((state) => ({
        conversationModelSelection: {
          ...state.conversationModelSelection,
          [conversationId]: selection,
        },
      }));
    },
    resetForNewChat: () => {
      set((state) => ({
        conversationModelSelection: {
          ...state.conversationModelSelection,
          "": DEFAULT_MODEL,
        },
      }));
    },
    clearModelSelection: (conversationId: string) => {
      set((state) => {
        const newMap = { ...state.conversationModelSelection };
        delete newMap[conversationId];
        return { conversationModelSelection: newMap };
      });
    },
  }),
);

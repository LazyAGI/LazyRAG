import { create } from "zustand";

/** 与后端约定一致的模型名，请求/解析时使用，不随界面语言切换。 */
export const MODEL_API_LABELS = {
  lazyRag: "LazyRAG 大模型",
  deepSeek: "DeepSeek",
} as const;

export type ModelSelectionType = "value_engineering" | "deepseek" | "both";

/** 选择器触发区短文案对应的 i18n 键 */
export const MODEL_SELECTION_SUMMARY_KEYS: Record<ModelSelectionType, string> = {
  value_engineering: "chat.modelSelectionTriggerLazyRag",
  deepseek: "chat.modelSelectionTriggerDeepSeek",
  both: "chat.dualModeCompare",
};

export const MODEL_OPTIONS = [
  {
    value: "value_engineering" as const,
    labelKey: "chat.lazyRagModel",
    descriptionKey: "chat.lazyRagModelDesc",
  },
  {
    value: "deepseek" as const,
    labelKey: "chat.deepSeekModel",
    descriptionKey: "chat.deepSeekModelDesc",
  },
] as const;

const DEFAULT_MODEL: ModelSelectionType = "value_engineering";


export function parseModelSelectionFromModels(
  models?: string[],
): ModelSelectionType {
  if (!models || models.length === 0) {
    return DEFAULT_MODEL;
  }

  const hasValueEngineering = models.some(
    (m) =>
      m === MODEL_API_LABELS.lazyRag ||
      m === "LazyRAG" ||
      m === "lazyRag",
  );
  const hasDeepSeek = models.some(
    (m) => m === MODEL_API_LABELS.deepSeek || m === "DeepSeek",
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
  
  conversationModelSelection: Record<string, ModelSelectionType>;
  
  getModelSelection: (conversationId: string) => ModelSelectionType;
  
  setModelSelection: (
    conversationId: string,
    selection: ModelSelectionType,
  ) => void;
  
  resetForNewChat: () => void;
  
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

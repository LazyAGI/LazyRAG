import { create } from "zustand";
import { persist } from "zustand/middleware";
import { ChatServiceApi } from "@/modules/chat/utils/request";

interface ConversationSettings {
  enableMultipleAnswers: boolean;
  setEnableMultipleAnswers: (enabled: boolean) => void;
  fetchSwitchStatus: () => Promise<void>; // 从服务器获取开关状态
  isLoading: boolean; // 是否正在加载状态
}

export const useConversationSettings = create<ConversationSettings>()(
  persist(
    (set, get) => ({
      enableMultipleAnswers: false,
      isLoading: false,
      setEnableMultipleAnswers: (enabled) =>
        set({ enableMultipleAnswers: enabled }),
      fetchSwitchStatus: async () => {
        // 如果正在加载，避免重复请求
        if (get().isLoading) {
          return;
        }

        set({ isLoading: true });
        try {
          const response =
            await ChatServiceApi().conversationServiceGetMultiAnswersSwitchStatus();
          const status = response.data.status ?? 0; // 默认为 0（关闭）
          // 将数字转换为布尔值：1 -> true, 0 -> false
          set({ enableMultipleAnswers: status === 1, isLoading: false });
        } catch (error) {
          console.error("获取双回复开关状态失败:", error);
          // 如果获取失败，保持当前状态不变
          set({ isLoading: false });
        }
      },
    }),
    {
      name: "conversation-settings",
      // 只持久化 enableMultipleAnswers，不持久化 isLoading
      partialize: (state) => ({
        enableMultipleAnswers: state.enableMultipleAnswers,
      }),
    },
  ),
);

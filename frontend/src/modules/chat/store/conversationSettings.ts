import { create } from "zustand";
import { persist } from "zustand/middleware";
import { ChatServiceApi } from "@/modules/chat/utils/request";

interface ConversationSettings {
  enableMultipleAnswers: boolean;
  setEnableMultipleAnswers: (enabled: boolean) => void;
  fetchSwitchStatus: () => Promise<void>;
  isLoading: boolean;
}

export const useConversationSettings = create<ConversationSettings>()(
  persist(
    (set, get) => ({
      enableMultipleAnswers: false,
      isLoading: false,
      setEnableMultipleAnswers: (enabled) =>
        set({ enableMultipleAnswers: enabled }),
      fetchSwitchStatus: async () => {
        if (get().isLoading) {
          return;
        }

        set({ isLoading: true });
        try {
          const response =
            await ChatServiceApi().conversationServiceGetMultiAnswersSwitchStatus();
          const status = response.data.status ?? 0;
          set({ enableMultipleAnswers: status === 1, isLoading: false });
        } catch (error) {
          set({ isLoading: false });
        }
      },
    }),
    {
      name: "conversation-settings",
      partialize: (state) => ({
        enableMultipleAnswers: state.enableMultipleAnswers,
      }),
    },
  ),
);

import { create } from "zustand";
import { persist } from "zustand/middleware";

interface ChatInputStore {
  inputContents: Record<string, string>;
  saveInputContent: (conversationId: string, content: string) => void;
  getInputContent: (conversationId: string) => string;
  clearInputContent: (conversationId: string) => void;
  clearAllInputContents: () => void;
}

export const useChatInputStore = create<ChatInputStore>()(
  persist(
    (set, get) => ({
      inputContents: {},
      saveInputContent: (conversationId: string, content: string) => {
        set((state) => ({
          inputContents: {
            ...state.inputContents,
            [conversationId]: content,
          },
        }));
      },
      getInputContent: (conversationId: string) => {
        return get().inputContents[conversationId] || "";
      },
      clearInputContent: (conversationId: string) => {
        set((state) => {
          const newContents = { ...state.inputContents };
          delete newContents[conversationId];
          return { inputContents: newContents };
        });
      },
      clearAllInputContents: () => {
        set({ inputContents: {} });
      },
    }),
    {
      name: "chat-input-contents",
      partialize: (state) => ({ inputContents: state.inputContents }),
    },
  ),
);

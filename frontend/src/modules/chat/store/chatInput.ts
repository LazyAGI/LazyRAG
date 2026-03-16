import { create } from "zustand";
import { persist } from "zustand/middleware";

interface ChatInputStore {
  // 存储每个会话的输入内容，key 为 conversationId，value 为输入内容
  inputContents: Record<string, string>;
  // 保存指定会话的输入内容
  saveInputContent: (conversationId: string, content: string) => void;
  // 获取指定会话的输入内容
  getInputContent: (conversationId: string) => string;
  // 清除指定会话的输入内容
  clearInputContent: (conversationId: string) => void;
  // 清除所有会话的输入内容
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
      // 只持久化 inputContents
      partialize: (state) => ({ inputContents: state.inputContents }),
    },
  ),
);

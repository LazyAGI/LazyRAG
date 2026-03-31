import { create } from "zustand";

interface ChatNewMessageStore {
  newMessage: boolean;
  setNewMessage: (newMessage: boolean) => void;
}

export const useChatNewMessageStore = create<ChatNewMessageStore>((set) => ({
  newMessage: true,
  setNewMessage: (newMessage: boolean) => set({ newMessage }),
}));

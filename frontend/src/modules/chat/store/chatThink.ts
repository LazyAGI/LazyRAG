import { create } from "zustand";
interface ChatThinkStore {
  think: boolean;
  setThink: (think: boolean) => void;
}

export const useChatThinkStore = create<ChatThinkStore>((set) => ({
  think: false,
  setThink: (think: boolean) => set({ think }),
}));

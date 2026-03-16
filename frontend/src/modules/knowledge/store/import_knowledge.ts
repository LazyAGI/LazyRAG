import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";

export const useImportKnowledgeStore = create()(
  subscribeWithSelector((set) => ({
    fileList: [],
    taskList: [],

    setFileList: (fileList: any[]) => {
      set({ fileList });
    },

    setTaskList: (taskList: any[]) => {
      set({ taskList });
    },
  })),
);

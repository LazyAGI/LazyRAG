import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";
import { Dataset, DatasetAclEnum } from "@/api/generated/knowledge-client";

interface DatasetPermissionState {
  currentDataset: Dataset | null;

  setCurrentDataset: (dataset: Dataset | null) => void;

  hasWritePermission: () => boolean;

  hasOnlyReadPermission: () => boolean;

  hasUploadPermission: () => boolean;

  clearDataset: () => void;

  getDatasetDetail: () => Dataset | null;
}

export const useDatasetPermissionStore = create<DatasetPermissionState>()(
  subscribeWithSelector((set, get) => ({
    currentDataset: null,

    setCurrentDataset: (dataset: Dataset | null) => {
      set({ currentDataset: dataset });
    },

    hasWritePermission: () => {
      const { currentDataset } = get();
      return (
        currentDataset?.acl?.includes(DatasetAclEnum.DatasetWrite) ?? false
      );
    },

    hasOnlyReadPermission: () => {
      const { currentDataset } = get();
      if (!currentDataset?.acl || currentDataset.acl.length === 0) {
        return false;
      }
      return (
        currentDataset.acl.includes(DatasetAclEnum.DatasetRead) &&
        !currentDataset.acl.includes(DatasetAclEnum.DatasetWrite) &&
        !currentDataset.acl.includes(DatasetAclEnum.DatasetUpload)
      );
    },

    hasUploadPermission: () => {
      const { currentDataset } = get();
      return (
        currentDataset?.acl?.includes(DatasetAclEnum.DatasetUpload) ?? false
      );
    },

    clearDataset: () => {
      set({ currentDataset: null });
    },

    getDatasetDetail: () => {
      return get().currentDataset;
    },
  })),
);

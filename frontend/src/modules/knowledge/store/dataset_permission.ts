import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";
import { Dataset, DatasetAclEnum } from "@/api/generated/knowledge-client";

interface DatasetPermissionState {
  // 当前知识库详情
  currentDataset: Dataset | null;

  // 设置当前知识库
  setCurrentDataset: (dataset: Dataset | null) => void;

  // 判断是否有写权限
  hasWritePermission: () => boolean;

  // 判断是否只有读权限
  hasOnlyReadPermission: () => boolean;

  // 判断是否有上传权限
  hasUploadPermission: () => boolean;

  // 清除权限信息
  clearDataset: () => void;

  // 获取当前知识库详情
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

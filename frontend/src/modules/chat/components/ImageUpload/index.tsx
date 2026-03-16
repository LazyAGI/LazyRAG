import React, { useState, forwardRef, useImperativeHandle } from "react";
import { Upload, message, Tooltip } from "antd";
import {
  RcFile,
  UploadChangeParam,
  UploadProps,
  UploadFile,
} from "antd/es/upload/interface";

import "./index.scss";
import { FileServiceApi } from "@/modules/chat/utils/request";
import { FileServiceApiFileServiceUploadFileRequest } from "@/api/generated/file-client";

export interface ImageUploadImperativeProps {
  removeFile: (uid?: string) => void;
  getFiles: () => (RcFile & { uri: string })[];
  clear: () => void;
  uploadFiles: (files: File[]) => void;
  getUploadingCount: () => number;
}

interface Props {
  max: number;
  types: string[];
  icon: React.ReactNode;
  updateFiles: (files: RcFile[]) => void;
  listNum: number;
  /** 上传前预处理：文档/图片互斥、Toast 等。返回 null 则按原逻辑处理 */
  onBeforeAddFiles?: (
    newFiles: File[],
    currentFiles: (RcFile & { uri?: string })[],
  ) => OnBeforeAddFilesResult;
}
interface FileItem extends RcFile {
  uri: string;
}

export const allowedImageTypes = [".png", ".jpg", ".jpeg"];
export const allowedFileTypes = [".pdf", ".docx", ".doc", ".pptx"];
export const allowedUploadTypes = [...allowedImageTypes, ...allowedFileTypes];

export type OnBeforeAddFilesResult = {
  filesToAdd: File[];
  clearFirst: boolean;
  toasts: string[];
} | null;

const ImageUpload = forwardRef<ImageUploadImperativeProps, Props>(
  (props, ref) => {
    const { max, types, icon, updateFiles, listNum, onBeforeAddFiles } = props;
    const [files, setFiles] = useState<FileItem[]>([]);
    const [uploadingCount, setUploadingCount] = useState(0);

    // 提取文件类型验证函数（支持 File 和 UploadFile 类型）
    const validateFileType = (
      file: File | UploadFile,
      allowedTypes: string[],
    ): boolean => {
      const ext = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
      if (!allowedTypes.includes(ext)) {
        message.warning(`仅支持上传${allowedTypes.join(",")}格式的文件`);
        return false;
      }
      return true;
    };

    // 提取文件大小验证函数（支持 File 和 UploadFile 类型）
    const validateFileSize = (file: File | UploadFile): boolean => {
      const ext = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
      const currentFileSizeMB = (file.size ?? 0) / 1024 / 1024;

      if (allowedImageTypes.includes(ext)) {
        if (currentFileSizeMB > 5) {
          message.error("上传文件大小不能超过 5 MB");
          return false;
        }
      }
      if (allowedFileTypes.includes(ext)) {
        if (currentFileSizeMB > 100) {
          message.error("上传文件大小不能超过 100 MB");
          return false;
        }
      }
      return true;
    };

    // 提取文件数量限制检查函数（支持 FileItem、RcFile 和 UploadFile 类型）
    const checkFileCountLimit = (
      currentFiles: FileItem[],
      newFile: FileItem | RcFile | UploadFile,
      maxCount: number,
    ): boolean => {
      // const tempGroup = Object.groupBy([...currentFiles, newFile], (item) => {
      //   const suffix = item.name.substring(item.name.lastIndexOf('.')).toLowerCase();
      //   return allowedImageTypes.includes(suffix) ? 'image' : 'file';
      // });
      // const tempGroup = Object.groupBy([...currentFiles, newFile], (item) => {
      //   const suffix = item.name.substring(item.name.lastIndexOf('.')).toLowerCase();
      //   return allowedImageTypes.includes(suffix) ? 'image' : 'file';
      // });

      // if ((tempGroup?.file?.length ?? 0) > 3) {
      //   message.warning('最多只能上传 3个文件');
      //   return false;
      // }
      // if ((tempGroup?.image?.length ?? 0) > 3) {
      //   message.warning('最多只能上传 3 张图片');
      //   return false;
      // }

      if ([...currentFiles, newFile].length > 3) {
        message.warning("最多只能上传 3个文件、图片");
        return false;
      }

      if (currentFiles.length >= maxCount) {
        // const ext = newFile.name.substring(newFile.name.lastIndexOf('.')).toLowerCase();
        // const maxTips1 = allowedImageTypes.includes(ext) ? '最多上传 3 张图片' : '最多只能上传 3个文件';
        message.warning("最多只能上传 3个文件、图片");
        return false;
      }

      return true;
    };

    // 提取文件上传函数（支持 RcFile 和 UploadFile 类型）
    const uploadFile = (
      file: RcFile | UploadFile,
      onSuccess?: (uri: string) => void,
      onError?: () => void,
    ) => {
      setUploadingCount((prev) => prev + 1);
      const data = {
        file,
        purpose: "chat",
        path: `/chat/${new Date().getTime()}/${file.name}`,
      } as unknown as FileServiceApiFileServiceUploadFileRequest;

      FileServiceApi()
        .fileServiceUploadFile(data, { timeout: 1 * 60 * 1000 })
        .then((res) => {
          setUploadingCount((prev) => prev - 1);
          onSuccess?.(res.data.filename || "");
        })
        .catch((error) => {
          console.error("文件上传失败:", error);
          message.error("文件上传失败，请重试");
          setUploadingCount((prev) => prev - 1);
          onError?.();
        });
    };

    const runAddFiles = (toAdd: File[], _baseFileList: FileItem[]) => {
      toAdd.forEach((file) => {
        const rcFile = file as RcFile;
        rcFile.uid = `rc-upload-${Date.now()}-${Math.random()}`;
        if (!validateFileType(file, types)) {
          return;
        }
        if (!validateFileSize(file)) {
          return;
        }
        setFiles((prev) => {
          if (!checkFileCountLimit(prev, rcFile, max)) {
            return prev;
          }
          const newFiles = [...prev, rcFile] as FileItem[];
          updateFiles?.(newFiles);
          uploadFile(
            rcFile,
            (uri) => {
              setFiles((prevFiles) =>
                prevFiles.map((f) => {
                  if (f.uid === rcFile.uid) {
                    f.uri = uri;
                  }
                  return f;
                }),
              );
            },
            () => {
              setFiles((prevFiles) =>
                prevFiles.filter((f) => f.uid !== rcFile.uid),
              );
            },
          );
          return newFiles;
        });
      });
    };

    const uploadProps: UploadProps = {
      multiple: false,
      showUploadList: false,
      disabled: listNum >= max,
      maxCount: max,
      accept: types.join(","),
      fileList: files,
      className: "chat-image-upload",
      beforeUpload: () => false,
      onChange: handleOnUploadChange,
    };

    useImperativeHandle(ref, () => ({
      removeFile: (uid?: string) => {
        if (uid) {
          onRemove(uid);
        }
      },
      getFiles: () => files,
      clear: () => setFiles([]),
      getUploadingCount: () => uploadingCount,
      uploadFiles: (droppedFiles: File[]) => {
        const current = [...files];
        const result = onBeforeAddFiles?.(droppedFiles, current);
        if (result) {
          result.toasts.forEach((t) => {
            if (t.includes("不支持")) {
              message.warning(t);
            } else {
              message.info(t);
            }
          });
          if (result.clearFirst) {
            setFiles([]);
            updateFiles?.([]);
          }
          runAddFiles(result.filesToAdd, result.clearFirst ? [] : current);
          return;
        }
        runAddFiles(droppedFiles, current);
      },
    }));

    function handleOnUploadChange(info: UploadChangeParam): string | void {
      const { file } = info;

      if (!validateFileType(file, types)) return Upload.LIST_IGNORE;
      if (!validateFileSize(file)) return Upload.LIST_IGNORE;

      const current = [...files];
      const result = onBeforeAddFiles?.([file as unknown as File], current);
      if (result) {
        result.toasts.forEach((t) => {
          if (t.includes("不支持")) {
            message.warning(t);
          } else {
            message.info(t);
          }
        });
        if (result.clearFirst) {
          setFiles([]);
          updateFiles?.([]);
        }
        if (result.filesToAdd.length > 0) {
          runAddFiles(result.filesToAdd, result.clearFirst ? [] : current);
        }
        return;
      }

      setFiles((prev) => {
        if (!checkFileCountLimit(prev, file, max)) {
          return prev;
        }
        const newFiles = [...prev, file] as FileItem[];
        updateFiles?.(newFiles);
        return newFiles;
      });
      uploadFile(file, (uri) => {
        setFiles((prev) =>
          prev.map((f) => {
            if (f.uid === file?.uid) {
              f.uri = uri;
            }
            return f;
          }),
        );
      });
    }

    function onRemove(uid: string) {
      setFiles((prev) => prev.filter((item: FileItem) => item.uid !== uid));
    }

    return (
      <Upload {...uploadProps}>
        <Tooltip placement="top" title="请勿上传超过3个文件、图片">
          {icon}
        </Tooltip>
      </Upload>
    );
  },
);

ImageUpload.displayName = "ImageUpload";

export default ImageUpload;

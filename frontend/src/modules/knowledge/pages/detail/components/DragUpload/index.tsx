import { Alert, message } from "antd";
import {
  DeleteOutlined,
  FileZipOutlined,
  InboxOutlined,
  InfoCircleFilled,
  PaperClipOutlined,
} from "@ant-design/icons";
import classNames from "classnames";
import { debounce, uniq } from "lodash";
import VirtualList from "rc-virtual-list";
import { ReactNode, useEffect, useRef, useState } from "react";
import { v4 as uuidv4 } from "uuid";

import { TaskOrigin } from "@/modules/knowledge/constants/common";
import FileUtils from "@/modules/knowledge/utils/file";
import "./index.scss";
import { compatibleUploadConfig } from "@/modules/knowledge/utils/batchUpload";
import RiskTip from "@/modules/knowledge/components/RiskTip";
import JSZip from "@progress/jszip-esm";

const ZIP_TOTAL_MAX_SIZE = 1 * 1024 * 1024 * 1024;
const ZIP_SINGLE_FILE_MAX_SIZE = 500 * 1024 * 1024;
const ZIP_ALLOWED_SUFFIX = ["pdf", "docx", "doc"];

export interface IDragUploadProps {
  value?: any[];
  onChange?: (value: any[]) => void;
  disabled?: boolean; // Disabled.
  maxCount?: number; // Total quantity.
  maxSize?: number; // Total size Unit B.
  maxFileSize?: number; // Single file size (unit: B).
  accept?: string[]; // Supported suffixes.
  title?: string; // Title.
  description?: ReactNode; // Description
  targetPath?: string; // The imported path is used with maxLevel to limit the total level.
  maxLevel?: number; // Maximum directory level.
  hiddenFileList?: boolean; // Hidden Files List.
  className?: string;
  taskOrigin?: TaskOrigin; // The default source of the task is the knowledge base.
  disableDragFolder?: boolean; // Disable dragging of folders.
  onZipStatusChange?: (hasError: boolean) => void;
  selectDirectory?: boolean; // Enable selecting directory via input.
  zipMode?: boolean; // Zip import mode.
  invalidTypeMessage?: string; // Unsupported type toast.
  invalidDropMessage?: string; // Invalid drop object toast.
}

const DragUpload = (props: IDragUploadProps) => {
  const {
    value = [],
    onChange = () => {},
    disabled,
    maxCount,
    maxSize,
    maxFileSize,
    accept,
    title,
    description,
    targetPath,
    maxLevel,
    hiddenFileList,
    className = "",
    taskOrigin,
    disableDragFolder,
    onZipStatusChange,
    selectDirectory,
    zipMode,
    invalidTypeMessage,
    invalidDropMessage,
  } = props;
  const [showAlert, setShowAlert] = useState(false);
  const dragFilesRef = useRef<any[]>([]);
  const singleUpload = maxCount === 1;
  const { ECompatibleFileState } = compatibleUploadConfig();
  const [zipStatusMap, setZipStatusMap] = useState<
    Record<string, { loading: boolean; error?: string }>
  >({});
  const dirAttrs: any = selectDirectory
    ? { webkitdirectory: "webkitdirectory", directory: "directory" }
    : {};

  useEffect(() => {
    value.forEach((file) => {
      if (
        file.path?.toLowerCase().endsWith(".zip") &&
        !zipStatusMap[file.uid] &&
        file.originFile
      ) {
        checkZip(file);
      }
    });
  }, [value]);

  useEffect(() => {
    if (onZipStatusChange) {
      const currentUids = new Set(value.map((f) => f.uid));
      const hasError = Object.entries(zipStatusMap).some(
        ([uid, status]) => currentUids.has(uid) && !!status.error,
      );
      onZipStatusChange(hasError);
    }
  }, [zipStatusMap, onZipStatusChange, value]);

  const checkZip = async (file: any) => {
    setZipStatusMap((prev) => ({ ...prev, [file.uid]: { loading: true } }));

    try {
      // @ts-ignore
      const zip = await new JSZip().loadAsync(file.originFile);

      // calculate total size
      let totalSize = 0;
      let hasSubFolder = false;
      let hasInvalidType = false;
      let hasOversizeFile = false;
      zip.forEach((_path: string, file: any) => {
        if (file?.dir) {
          return;
        }
        const normalizedPath = (_path || "").replace(/\\/g, "/");
        if (normalizedPath.includes("/")) {
          hasSubFolder = true;
        }
        const fileName = normalizedPath.split("/").pop() || normalizedPath;
        const suffix = FileUtils.getSuffix(fileName);
        if (!ZIP_ALLOWED_SUFFIX.includes(suffix)) {
          hasInvalidType = true;
        }
        // @ts-ignore
        const fileSize = file._data?.uncompressedSize || 0;
        if (fileSize > ZIP_SINGLE_FILE_MAX_SIZE) {
          hasOversizeFile = true;
        }
        totalSize += fileSize;
      });

      if (hasSubFolder) {
        message.warning(
          "zip压缩包仅支持根目录的文件，一级及以上文件夹将被忽略",
        );
      }
      if (hasInvalidType) {
        message.warning("仅传入pdf、docx、doc格式的文件");
      }

      if (hasOversizeFile) {
        setZipStatusMap((prev) => ({
          ...prev,
          [file.uid]: {
            loading: false,
            error: "压缩包中单个文件不能超过500MB",
          },
        }));
        return;
      }

      if (totalSize > ZIP_TOTAL_MAX_SIZE) {
        setZipStatusMap((prev) => ({
          ...prev,
          [file.uid]: { loading: false, error: "文件过大，请拆分后上传" },
        }));
        return;
      }

      setZipStatusMap((prev) => ({ ...prev, [file.uid]: { loading: false } }));
    } catch (e) {
      const isEncrypted =
        e?.toString() === "Error: Encrypted zip are not supported";

      if (isEncrypted) {
        setZipStatusMap((prev) => ({
          ...prev,
          [file.uid]: {
            loading: false,
            error: "压缩包已加密，暂不支持加密文件",
          },
        }));
        return;
      }
      setZipStatusMap((prev) => ({
        ...prev,
        [file.uid]: { loading: false, error: "文件已损坏" },
      }));
    }
  };

  const handleChange = (fileList: any[]) => {
    // 获取路径中的根文件夹名称 (例如: 'folder/file.txt' -> 'folder')
    const getRootFolderName = (path: string) => {
      const parts = path?.split("/") || [];
      return parts.length > 1 ? parts[0] : null;
    };

    // 确定唯一允许的根文件夹：
    // 1. 优先使用已存在文件列表(value)中的根文件夹
    // 2. 若无，则使用新上传列表(fileList)中的第一个文件夹
    const rootFolder =
      value.map((i) => getRootFolderName(i.path)).find(Boolean) ||
      fileList.map((i) => getRootFolderName(i.path)).find(Boolean);

    let filteredFileList = fileList;
    if (rootFolder) {
      // 检查文件是否不属于当前根文件夹
      const isInvalidFile = (item: any) => {
        const folder = getRootFolderName(item.path);
        // 如果该文件在某个文件夹内，且该文件夹不是当前的 rootFolder，则视为非法
        return folder && folder !== rootFolder;
      };

      // 如果存在非法文件，弹出警告并过滤
      if (fileList.some(isInvalidFile)) {
        message.warning("仅支持单次选择1个文件夹");
        filteredFileList = fileList.filter((item) => !isInvalidFile(item));
      }
    }

    const newFileList: any[] = [];
    const errorList: string[] = [];
    let totalSize = value.reduce((prev, cur) => prev + cur.size, 0);
    let totalCount = value.length;
    let hasInvalidType = false;
    filteredFileList.forEach((item) => {
      // File already exists.
      if (value.some((i) => i.path === item.path)) {
        return;
      }

      // Unsupported format.
      if (accept && !accept.includes(FileUtils.getSuffix(item.path))) {
        hasInvalidType = true;
        return;
      }

      if (maxFileSize && item.size > maxFileSize) {
        errorList.push(
          `单个文件不能超过${FileUtils.formatFileSize(maxFileSize, 0)}`,
        );
        return;
      }

      if (maxLevel) {
        const pathArr = (targetPath?.split("/") || []).concat(
          item.path?.split("/") || [],
        );
        if (pathArr.length > maxLevel) {
          setShowAlert(true);
          return;
        }
      }

      totalSize += item.size;
      if (maxSize && totalSize > maxSize) {
        errorList.push(`总大小不能超过${FileUtils.formatFileSize(maxSize, 0)}`);
        return;
      }

      totalCount += 1;
      if (!singleUpload && maxCount && totalCount > maxCount) {
        errorList.push(`总数量不能超过${maxCount}个`);
        return;
      }

      newFileList.push(item);
    });

    if (hasInvalidType) {
      errorList.push(invalidTypeMessage || "文件格式不支持");
    }

    uniq(errorList).forEach((err) => {
      message.error(err);
    });

    if (!newFileList.length) {
      return;
    }

    if (singleUpload) {
      onChange(newFileList.slice(0, 1));
    } else {
      onChange([...newFileList, ...value]);
    }
  };

  const addSelectFiles = (files: FileList | null) => {
    const newFileList: any[] = [];
    for (const file of Array.from(files || [])) {
      // 过滤 mac/系统隐藏文件，避免“上传成功但仍提示格式不支持”
      const relativePath = file.webkitRelativePath || file.name;
      const fileName = relativePath.split("/").pop() || "";
      if (fileName === ".DS_Store" || fileName.startsWith("._")) {
        continue;
      }
      const newFile = {
        uid: uuidv4(),
        path: relativePath,
        size: file.size,
        state: ECompatibleFileState.UploadPending,
        percent: 0,
        originFile: file,
        taskId: "",
        taskOrigin,
      };
      newFileList.push(newFile);
    }
    handleChange(newFileList);
  };

  const addDragFiles = debounce(() => {
    handleChange(dragFilesRef.current);
    dragFilesRef.current = [];
  }, 100);

  const dragUpload = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (disabled) {
      return;
    }

    let hasBlockedEntry = false;
    for (const item of Array.from(e.dataTransfer?.items || [])) {
      if (item.kind === "file") {
        const entry = item.webkitGetAsEntry();
        if (!entry) {
          continue;
        }
        if (zipMode && entry.isDirectory) {
          hasBlockedEntry = true;
          continue;
        }
        if (!selectDirectory && !zipMode && entry.isDirectory) {
          hasBlockedEntry = true;
          continue;
        }
        if (selectDirectory && entry.isFile) {
          hasBlockedEntry = true;
          continue;
        }
        getFileFormEntry(entry);
      }
    }
    if (hasBlockedEntry) {
      message.error(invalidDropMessage || "拖拽内容不支持");
    }
  };

  const getFileFormEntry = (entry: FileSystemEntry | null) => {
    if (entry?.isFile) {
      (entry as any).file((file: { name: string; size: any }) => {
        if (file.name === ".DS_Store") {
          return;
        }
        dragFilesRef.current.push({
          uid: uuidv4(),
          path: entry.fullPath.slice(1),
          size: file?.size,
          state: ECompatibleFileState.UploadPending,
          percent: 0,
          originFile: file,
          taskId: "",
          taskOrigin,
        });
        addDragFiles();
      });
    }

    if (entry?.isDirectory && !disableDragFolder) {
      const reader = (entry as any).createReader();
      readDir(reader);
    }
  };

  const readDir = (dirReader: {
    readEntries: (arg0: (entries: any[]) => void) => void;
  }) => {
    dirReader.readEntries((entries: any[]) => {
      entries.forEach((v) => {
        getFileFormEntry(v);
      });
      if (entries.length > 0) {
        readDir(dirReader);
      }
    });
  };

  const deleteFile = (file: any) => {
    const newFiles = value.filter((v) => v.uid != file.uid);
    onChange(newFiles);
  };

  return (
    <>
      <label>
        <div
          className={classNames(
            "dragContainer",
            disabled ? "disabled" : "",
            className ? className : "",
          )}
          onDragEnter={(e) => e.preventDefault()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={dragUpload}
        >
          <InboxOutlined className="uploadIcon" style={{ fontSize: 48 }} />
          <div className="drag-title">
            <span style={{ marginRight: 4 }}>
              {title || (
                <>
                  拖拽至此上传或{" "}
                  <span className="drag-text">
                    {selectDirectory ? "选择文件夹" : "选择文件"}
                  </span>
                </>
              )}
            </span>
            <RiskTip />
          </div>
          <div className="description">{description}</div>
        </div>
        <input
          type="file"
          value={[]}
          multiple={!singleUpload}
          style={{ display: "none" }}
          disabled={disabled}
          onChange={(e) => addSelectFiles(e.target.files)}
          accept={accept?.map((i) => `.${i}`).join(",")}
          {...dirAttrs}
        />
      </label>
      {showAlert && (
        <Alert
          message="已过滤嵌套文件夹"
          type="warning"
          showIcon
          closable
          onClose={() => setShowAlert(false)}
          style={{ marginTop: 4 }}
        />
      )}
      {!hiddenFileList && (
        <VirtualList
          data={value}
          height={Math.min(200, value.length * 30)}
          itemHeight={30}
          itemKey="uid"
          style={{ marginTop: 4 }}
        >
          {(file) => {
            const error = zipStatusMap[file.uid]?.error;
            return (
              <div className="fileItem" key={file.uid}>
                {file.path?.toLowerCase().endsWith(".zip") ? (
                  <FileZipOutlined />
                ) : (
                  <PaperClipOutlined />
                )}
                <div title={file.path} className="fileName">
                  <span className={classNames("filePath", { error })}>
                    {file.path}
                  </span>
                  {error && (
                    <span
                      style={{
                        color: "#ff4d4f",
                        marginLeft: 8,
                        fontSize: 12,
                        float: "right",
                      }}
                    >
                      <InfoCircleFilled style={{ marginRight: 4 }} />
                      {error}
                    </span>
                  )}
                </div>
                <DeleteOutlined
                  className="deleteIcon"
                  onClick={() => deleteFile(file)}
                />
              </div>
            );
          }}
        </VirtualList>
      )}
    </>
  );
};

export default DragUpload;

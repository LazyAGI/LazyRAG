import { v4 as uuidv4 } from "uuid";

import { FileState } from "@/modules/knowledge/constants/common";
import { useImportKnowledgeStore } from "@/modules/knowledge/store/import_knowledge";
import FileUtils from "./file";
import { JobServiceApi } from "./request";
import { StartJobRequestStartModeEnum } from "@/api/generated/knowledge-client";
import {
  JobJobStateEnum,
  DocumentInfoDocumentErrorEnum,
  DocumentInfoDocumentStateEnum,
} from "@/api/generated/knowledge-client";

const CHUNK_SIZE = 10 * 1024 * 1024;
const MAX_UPLOADING_NUM = 6;
const MAX_RETRY_COUNT = 2;

export const compatibleUploadConfig = () => {
  return {
    ECompatibleFileState: {
      UploadPending: FileState.UPLOAD_PENDING,
      Uploading: FileState.UPLOADING,
      Success: FileState.PARSE_PENDING,
      Fail: FileState.FAIL,
      Cancel: FileState.CANCEL,
    },
    ECompatiblTaskState: {
      Uploading: JobJobStateEnum.Creating,
      JobStarted: JobJobStateEnum.Parsing,
      Fail: JobJobStateEnum.Failed,
      Cancel: JobJobStateEnum.Cancelled,
      Success: JobJobStateEnum.Succeeded,
    },
    CompatibleAPI: {
      batchGetPresignURL: JobServiceApi().jobServiceBatchPresignUploadFileURL,
      getMultipartPresignURL:
        JobServiceApi().jobServicePresignMultipartUploadFileURL,
      completeMultipart: JobServiceApi().jobServiceCompleteMultipartUploadFile,
      startImportTask: JobServiceApi().jobServiceStartJob,
      cancelTaskWithKeepalive: JobServiceApi().jobServiceCancelJob,
    },
  };
};

class BatchUpload {
  get localTaskList(): any[] {
    return useImportKnowledgeStore.getState().taskList || [];
  }

  get fileList(): any[] {
    return useImportKnowledgeStore.getState().fileList || [];
  }

  get pendingFile() {
    const file = this.fileList.find((file) => {
      const { ECompatibleFileState } = compatibleUploadConfig();
      return file.state === ECompatibleFileState.UploadPending;
    });
    return file;
  }

  public getFileById = (uid?: string) => {
    return this.fileList.find((item) => item.uid === uid);
  };

  public getTaskById = (taskId?: string) => {
    return this.localTaskList.find((item) => item.id === taskId);
  };

  public init = () => {
    this.bindEvents();
  };

  
  public addTask = (params: {
    task: any;
    fileList: any[];
    priority?: boolean;
    startMode?: StartJobRequestStartModeEnum;
  }) => {
    const { task, fileList, priority, startMode } = params;
    const taskWithStartMode = { ...task, startMode };
    const newTaskList = [...this.localTaskList, taskWithStartMode];
    const newFileList = priority
      ? [...fileList, ...this.fileList]
      : [...this.fileList, ...fileList];
    this.updateTaskList(newTaskList);
    this.updateFileList(newFileList);
    this.getUploadUrl({
      task: taskWithStartMode,
      pendingList: fileList,
      startMode,
    });
  };

  public cancelUpload = (taskId?: string) => {
    const task = this.getTaskById(taskId);
    if (!task) {
      return;
    }
    const { ECompatibleFileState, ECompatiblTaskState } =
      compatibleUploadConfig();
    const newTaskList = this.localTaskList.map((item) => {
      if (item.id === taskId) {
        return { ...item, taskState: ECompatiblTaskState.Cancel };
      }
      return item;
    });
    const newFileList = this.fileList.map((item) => {
      if (item.taskId === taskId) {
        return { ...item, state: ECompatibleFileState.Cancel };
      }
      return item;
    });
    this.updateTaskList(newTaskList);
    this.updateFileList(newFileList);
  };

  public getUploadUrl = (params: {
    task: any;
    pendingList: any[];
    startMode?: StartJobRequestStartModeEnum;
  }) => {
    const { task, pendingList, startMode } = params;
    const { ECompatibleFileState, CompatibleAPI } = compatibleUploadConfig();
    const smallFiles = pendingList.filter(
      (file) =>
        file.size <= CHUNK_SIZE &&
        file.state === ECompatibleFileState.UploadPending,
    );
    if (!smallFiles.length) {
      this.starBatchUpload(startMode);
      return;
    }

    CompatibleAPI.batchGetPresignURL({
      job: task.id,
      batchPresignUploadFileURLRequest: {
        job: task.id,
        rel_path: smallFiles.map((file) => file.path),
      },
    })
      .then((res) => {
        const newFileList = this.fileList.map((file) => {
          if (smallFiles.some((i) => i.uid === file.uid)) {
            const uploadUrl = res.data.result?.[file.path];
            return {
              ...file,
              uploadUrl,
              state: uploadUrl ? file.state : ECompatibleFileState.Fail,
            };
          }
          return file;
        });
        this.updateFileList(newFileList);
      })
      .finally(() => {
        this.starBatchUpload(startMode);
      });
  };

  private starBatchUpload = (startMode?: StartJobRequestStartModeEnum) => {
    const uploadingNum = this.fileList.reduce((prev, cur) => {
      const { ECompatibleFileState } = compatibleUploadConfig();
      if (
        cur.state === ECompatibleFileState.Uploading &&
        cur.size <= CHUNK_SIZE
      ) {
        return prev + 1;
      }
      return prev;
    }, 0);
    for (let i = 0; i < MAX_UPLOADING_NUM - uploadingNum; i++) {
      this.uploadPendingFile(startMode);
    }
  };

  private uploadPendingFile = (startMode?: StartJobRequestStartModeEnum) => {
    const file = this.pendingFile;
    if (!file) {
      return;
    }
    const fileId = file.uid;
    const { ECompatibleFileState } = compatibleUploadConfig();

    if (file.isChunk) {
      this.updateFile(fileId, { state: ECompatibleFileState.Uploading });
      this.chunkUpload(fileId);
      return;
    }

    if (file.size > CHUNK_SIZE) {
      this.updateFile(fileId, { state: ECompatibleFileState.Uploading });
      this.createChunk(fileId);
      return;
    }

    if (file.uploadUrl) {
      this.updateFile(fileId, { state: ECompatibleFileState.Uploading });
      this.directUpload(fileId, startMode);
    }
  };

  private createChunk = (fileId: string) => {
    const file = this.getFileById(fileId);
    const task = this.getTaskById(file.taskId);
    const { ECompatibleFileState, CompatibleAPI } = compatibleUploadConfig();
    CompatibleAPI.getMultipartPresignURL({
      job: task.id,
      presignMultipartUploadFileURLRequest: {
        job: task.id,
        relpath: file.path,
        file_size: file.size,
      },
    })
      .then((res) => {
        const chunkList = [];
        for (let i = 0; i < (res.data.list?.length || 0); i++) {
          const item = res.data.list?.[i];
          const chunk = file.originFile.slice(
            Number(item?.file_offset),
            Number(item?.file_offset) + Number(item?.part_size),
          );
          const newFile = {
            ...this.getFileById(fileId),
            uid: uuidv4(),
            originFile: chunk,
            uploadUrl: item?.uri,
            size: chunk.size,
            isChunk: true,
            parentUid: file.uid,
            chunkNum: item?.part_num,
            uploadId: res.data.upload_id,
            state: ECompatibleFileState.UploadPending,
          };
          chunkList.push(newFile);
        }
        const parentIndex = this.fileList.findIndex(
          (item) => item.uid === fileId,
        );
        const newFileList = [...this.fileList];
        newFileList.splice(
          parentIndex,
          1,
          { ...this.fileList[parentIndex], originFile: undefined as any },
          ...chunkList,
        );
        this.updateFileList(newFileList);
        this.starBatchUpload();
      })
      .catch(() => {
        this.updateFile(fileId, {
          state: ECompatibleFileState.Fail,
          err: DocumentInfoDocumentErrorEnum.OssException,
        });
        this.uploadPendingFile();
        this.completeTask(file.taskId);
      });
  };

  private directUpload = (
    fileId: string,
    startMode?: StartJobRequestStartModeEnum,
  ) => {
    const file = this.getFileById(fileId);
    const { ECompatibleFileState } = compatibleUploadConfig();
    FileUtils.putFile({ file: file.originFile, url: file.uploadUrl })
      .then(() => {
        this.updateFile(fileId, { percent: 100 });
        const now = Date.now();
        setTimeout(() => {
          this.updateFile(fileId, {
            state: ECompatibleFileState.Success,
            percent: 100,
            finishTime: now,
          });
          this.completeTask(file.taskId, startMode);
        }, 300);
      })
      .catch(() => {
        if (file.retryCount >= MAX_RETRY_COUNT) {
          this.updateFile(fileId, {
            state: ECompatibleFileState.Fail,
            err: DocumentInfoDocumentErrorEnum.OssException,
          });
        } else {
          this.updateFile(fileId, {
            state: ECompatibleFileState.UploadPending,
            retryCount: (file.retryCount || 0) + 1,
          });
        }
        this.completeTask(file.taskId, startMode);
      })
      .finally(() => {
        this.uploadPendingFile();
      });
  };

  private chunkUpload = (chunkId: string) => {
    const chunk = this.getFileById(chunkId);
    const { ECompatibleFileState } = compatibleUploadConfig();
    FileUtils.putFile({ file: chunk.originFile, url: chunk.uploadUrl })
      .then((response) => {
        this.updateFile(chunkId, {
          state: ECompatibleFileState.Success,
          etag: response.headers.get("Etag") || "",
        });
      })
      .catch(() => {
        if (chunk.retryCount >= MAX_RETRY_COUNT) {
          this.updateFile(chunkId, {
            state: ECompatibleFileState.Fail,
            err: DocumentInfoDocumentErrorEnum.OssException,
          });
        } else {
          this.updateFile(chunkId, {
            state: ECompatibleFileState.UploadPending,
            retryCount: (chunk.retryCount || 0) + 1,
          });
        }
      })
      .finally(() => {
        this.completeChunk(chunkId);
        this.uploadPendingFile();
      });
  };

  private completeChunk = (chunkId: string) => {
    const chunk = this.getFileById(chunkId);
    const parentFile = this.getFileById(chunk.parentUid);
    const { ECompatibleFileState, CompatibleAPI } = compatibleUploadConfig();

    if (!parentFile || parentFile.state !== ECompatibleFileState.Uploading) {
      return;
    }

    const allChunks = this.fileList.filter(
      (item) => item.parentUid === chunk.parentUid,
    );
    const { successNum, failedNum, err } = allChunks.reduce(
      (prev: any, cur) => {
        if (cur.state === ECompatibleFileState.Success) {
          prev.successNum += 1;
        }
        if (cur.state === ECompatibleFileState.Fail) {
          prev.failedNum += 1;
          prev.err = cur.err || prev.err;
        }
        return prev;
      },
      { successNum: 0, failedNum: 0, err: undefined },
    );

    if (failedNum > 0) {
      const newFileList = this.fileList.map((item) => {
        if (
          item.parentUid === chunk.parentUid ||
          item.uid === chunk.parentUid
        ) {
          return { ...item, state: ECompatibleFileState.Fail, err };
        }
        return item;
      });
      this.updateFileList(newFileList);
      this.completeTask(chunk.taskId);
      return;
    }

    this.updateFile(chunk.parentUid, {
      percent: Math.round((successNum / allChunks.length) * 100),
    });
    if (successNum < allChunks.length) {
      return;
    }

    const task = this.getTaskById(chunk.taskId);
    CompatibleAPI.completeMultipart({
      job: task.id,
      completeMultipartUploadFileRequest: {
        job: task.id,
        upload_id: chunk.uploadId,
        relpath: chunk.path,
        list: allChunks.map((item) => ({
          partNum: item.chunkNum,
          etag: item.etag,
        })),
      },
    })
      .then(() => {
        this.updateFile(chunk.parentUid, {
          state: ECompatibleFileState.Success,
          percent: 100,
          finishTime: Date.now(),
        });
      })
      .catch(() => {
        this.updateFile(chunk.parentUid, {
          state: ECompatibleFileState.Fail,
          err: DocumentInfoDocumentErrorEnum.OssException,
        });
      })
      .finally(() => {
        this.completeTask(chunk.taskId);
      });
  };

  private completeTask = (
    taskId: string,
    startMode?: StartJobRequestStartModeEnum,
  ) => {
    const task = this.getTaskById(taskId);
    const effectiveStartMode = startMode ?? task?.startMode;

    if (!task || task.skipCompleteTask) {
      return;
    }
    const { ECompatibleFileState, ECompatiblTaskState, CompatibleAPI } =
      compatibleUploadConfig();
    if (task.taskState !== ECompatiblTaskState.Uploading) {
      return;
    }

    const allFiles = this.fileList.filter(
      (item) => item.taskId === taskId && !item.isChunk,
    );
    const hasUploadingFile = allFiles.some((file) => {
      return [
        ECompatibleFileState.UploadPending,
        ECompatibleFileState.Uploading,
      ].includes(file.state);
    });
    if (hasUploadingFile) {
      return;
    }

    const { failedCount, failedSize, failedFiles } = allFiles.reduce(
      (prev: any, cur) => {
        if (cur.state === ECompatibleFileState.Fail) {
          prev.failedCount += 1;
          prev.failedSize += cur.size;
          if (prev.failedFiles.length < 100) {
            prev.failedFiles.push({
              displayName: cur.path,
              documentSize: cur.size,
              documentState: cur.state,
              documentError: cur.err,
            });
          }
        }
        return prev;
      },
      { failedCount: 0, failedSize: 0, failedFiles: [] },
    );

    CompatibleAPI.startImportTask({
      dataset: task.datasetId,
      job: taskId,
      startJobRequest: {
        name: "",
        documents: failedFiles,
        failed_file_size: failedSize,
        failed_file_count: failedCount,
        document_id: task.documentId,
        start_mode: effectiveStartMode,
      },
    })
      .then(() => {
        this.updateTask({ ...task, taskState: ECompatiblTaskState.JobStarted });
      })
      .catch(() => {
        this.updateTask({ ...task, taskState: ECompatiblTaskState.Fail });
      });
  };

  private updateFile = (fileId: string, newParams: any) => {
    const newFileList = this.fileList.map((file) => {
      if (file.uid === fileId) {
        return { ...file, ...newParams };
      }
      return file;
    });
    this.updateFileList(newFileList);
  };

  public updateFileList = (newFileList: any[]) => {
    newFileList = newFileList.map((item) => {
      const { ECompatibleFileState } = compatibleUploadConfig();
      return {
        ...item,
        originFile: [
          ECompatibleFileState.Success,
          ECompatibleFileState.Fail,
          ECompatibleFileState.Cancel,
        ].includes(item.state)
          ? (undefined as any)
          : item.originFile,
      };
    });
    useImportKnowledgeStore.setState({ fileList: newFileList });
  };

  public updateTask = (newTask: any) => {
    const newTaskList = this.localTaskList.map((task) => {
      if (task.id === newTask.id) {
        return newTask;
      }
      return task;
    });
    this.updateTaskList(newTaskList);
  };

  private updateTaskList = (newTaskList: any[]) => {
    useImportKnowledgeStore.setState({ taskList: newTaskList });
  };

  private beforeUnload = (e: any) => {
    const hasUploadingTask = this.localTaskList.some((item) => {
      const { ECompatiblTaskState } = compatibleUploadConfig();
      return item.taskState === ECompatiblTaskState.Uploading;
    });
    if (hasUploadingTask) {
      e.preventDefault();
      e.returnValue = "";
    }
  };

  public unload = () => {
    const newTaskList = this.localTaskList.map((item) => {
      const { ECompatiblTaskState, CompatibleAPI } = compatibleUploadConfig();
      if (item.taskState === ECompatiblTaskState.Uploading) {
        CompatibleAPI.cancelTaskWithKeepalive({
          dataset: item.datasetId,
          job: item.id,
          cancelJobRequest: {
            name: "",
          },
        });
      }
      return { ...item, taskState: ECompatiblTaskState.Cancel };
    });
    const newFileList = this.fileList.map((item) => {
      const { ECompatibleFileState } = compatibleUploadConfig();
      return { ...item, state: ECompatibleFileState.Cancel };
    });
    this.updateTaskList(newTaskList);
    this.updateFileList(newFileList);
  };

  private bindEvents = () => {
    window.addEventListener("beforeunload", this.beforeUnload);
    window.addEventListener("unload", this.unload);
  };
}

const batchUpload = new BatchUpload();
export default batchUpload;

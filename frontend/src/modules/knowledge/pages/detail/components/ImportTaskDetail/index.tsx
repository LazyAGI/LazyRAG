import {
  Button,
  Form,
  FormItemProps,
  message,
  Modal,
  Radio,
  Progress,
  Table,
} from "antd";
import { CloseOutlined, ArrowLeftOutlined } from "@ant-design/icons";
import { useEffect, useRef, useState } from "react";
import { v4 as uuidv4 } from "uuid";
import moment from "moment";

import {
  TABLE_PAGE_SIZE,
  TIME_FORMAT,
} from "@/modules/knowledge/constants/common";
import { STATUS_COLORS, FileTabs } from "@/modules/knowledge/constants/common";
import FileUtils from "@/modules/knowledge/utils/file";
import StatusTag from "../StatusTag";
import ElapsedTime from "../ElapsedTime";
import "./index.scss";
import { useImportKnowledgeStore } from "@/modules/knowledge/store/import_knowledge";
import Polling from "@/modules/knowledge/utils/polling";
import { JobServiceApi } from "@/modules/knowledge/utils/request";
import {
  JobJobStateEnum,
  DocumentInfoDocumentErrorEnum,
  DocumentInfoDocumentStateEnum,
} from "@/api/generated/knowledge-client";

interface IProps {
  datasetId: string;
  jobId: string;
  onBack: () => void;
  onClose: () => void;
  defaultTab?: string;
}

const FailedFileStates = [
  DocumentInfoDocumentStateEnum.DocumentStageUnspecified,
  DocumentInfoDocumentStateEnum.DocumentFailed,
  DocumentInfoDocumentStateEnum.DocumentCrawlingFailed,
  DocumentInfoDocumentStateEnum.DocumentParsingFailed,
  DocumentInfoDocumentStateEnum.DocumentParsingCancelled,
];

const FileTabInfo = [
  {
    id: FileTabs.RUNNING,
    fileStates: [
      DocumentInfoDocumentStateEnum.DocumentParsing,
      DocumentInfoDocumentStateEnum.DocumentQueued,
      DocumentInfoDocumentStateEnum.DocumentCrawling,
      DocumentInfoDocumentStateEnum.DocumentCrawlingQueued,
    ],
  },
  {
    id: FileTabs.SUCCESS,
    fileStates: [DocumentInfoDocumentStateEnum.DocumentParseSuccessfully],
  },
  {
    id: FileTabs.FAILED,
    fileStates: FailedFileStates,
  },
];

const DetailItem = (props: FormItemProps) => {
  const { children, ...rest } = props;
  return (
    <Form.Item {...rest}>
      {!children ||
      (children instanceof Array && children.length === 0) ||
      [0, "0", "0B"].includes(children)
        ? "-"
        : children}
    </Form.Item>
  );
};

const ImportTaskDetail = (props: IProps) => {
  const { datasetId, jobId, onBack, onClose, defaultTab } = props;

  const [detail, setDetail] = useState({});
  const [page, setPage] = useState(1);
  const [tab, setTab] = useState(defaultTab || FileTabs.RUNNING);

  const pollingRef = useRef(new Polling());

  const { fileList, taskList } = useImportKnowledgeStore();
  const localTask = taskList.find((item: any) => item.id === jobId);
  // All local files of current task.
  const localFiles = fileList.filter(
    (item: any) => item.taskId === jobId && !item.isChunk,
  );
  // Local file uploading.
  const isLocalUploading = localTask?.taskState === JobJobStateEnum.Creating;
  // Task running.
  const isRunning =
    isLocalUploading || detail.job_state === JobJobStateEnum.Parsing;
  // File status corresponding to tab.
  const fileStates = FileTabInfo.find((item) => item.id === tab)?.fileStates;
  const partSuccess =
    detail.job_state === JobJobStateEnum.PartialSuccess &&
    detail.job_info.failed_document_count > 0;

  const FileErrors = [
    {
      id: DocumentInfoDocumentErrorEnum.DocumentErrorUnspecified,
      title: "内部服务错误",
    },
    {
      id: DocumentInfoDocumentErrorEnum.UnsupportedFormat,
      title: "当前暂未支持该文件解析",
    },
    {
      id: DocumentInfoDocumentErrorEnum.UnsupportedWebsiteCrawling,
      title: "不支持抓取该网站",
    },
    {
      id: DocumentInfoDocumentErrorEnum.OtherTechnicalReasons,
      title: "其他技术原因",
    },
    { id: DocumentInfoDocumentErrorEnum.DownloadFailure, title: "下载失败" },
    { id: DocumentInfoDocumentErrorEnum.StorageFailure, title: "存储失败" },
    { id: DocumentInfoDocumentErrorEnum.StorageTimeout, title: "存储超时" },
    { id: DocumentInfoDocumentErrorEnum.UploadFailure, title: "上传失败" },
    {
      id: DocumentInfoDocumentErrorEnum.DatabaseException,
      title: "数据库异常",
    },
    {
      id: DocumentInfoDocumentErrorEnum.DocumentStorageAccessException,
      title: "文档存储访问异常",
    },
    { id: DocumentInfoDocumentErrorEnum.OssException, title: "对象存储错误" },
    {
      id: DocumentInfoDocumentErrorEnum.FileContentException,
      title: "文件内容异常",
    },
  ];

  const FileStates = [
    {
      id: DocumentInfoDocumentStateEnum.DocumentStageUnspecified,
      title: "失败",
      color: STATUS_COLORS.error,
    },
    {
      id: DocumentInfoDocumentStateEnum.DocumentQueued,
      title: "导入中",
      color: STATUS_COLORS.progress,
    },
    {
      id: DocumentInfoDocumentStateEnum.DocumentParsing,
      title: "解析中",
      color: STATUS_COLORS.progress,
    },
    {
      id: DocumentInfoDocumentStateEnum.DocumentParseSuccessfully,
      title: "成功",
      color: STATUS_COLORS.success,
    },
    {
      id: DocumentInfoDocumentStateEnum.DocumentParsingFailed,
      title: "失败",
      color: STATUS_COLORS.error,
    },
    {
      id: DocumentInfoDocumentStateEnum.DocumentParsingCancelled,
      title: "已取消",
      color: STATUS_COLORS.error,
    },
    {
      id: DocumentInfoDocumentStateEnum.DocumentCrawling,
      title: "采集中",
      color: STATUS_COLORS.progress,
    },
    {
      id: DocumentInfoDocumentStateEnum.DocumentCrawlingFailed,
      title: "采集失败",
      color: STATUS_COLORS.error,
    },
    {
      id: DocumentInfoDocumentStateEnum.DocumentFailed,
      title: "上传失败",
      color: STATUS_COLORS.error,
    },
    {
      id: DocumentInfoDocumentStateEnum.DocumentCrawlingQueued,
      title: "采集排队中",
      color: STATUS_COLORS.offline,
    },
  ];

  const TaskStates = [
    {
      title: "创建中",
      taskStates: [JobJobStateEnum.Creating],
      color: STATUS_COLORS.progress,
    },
    {
      title: "解析中",
      taskStates: [JobJobStateEnum.Parsing],
      color: STATUS_COLORS.progress,
    },
    {
      title: "成功",
      taskStates: [JobJobStateEnum.Succeeded],
      color: STATUS_COLORS.success,
    },
    {
      title: "失败",
      taskStates: [JobJobStateEnum.Failed],
      color: STATUS_COLORS.error,
    },
    {
      title: "已取消",
      taskStates: [JobJobStateEnum.Cancelled],
      color: STATUS_COLORS.error,
    },
    {
      title: "部分成功",
      taskStates: [JobJobStateEnum.PartialSuccess],
      color: STATUS_COLORS.warning,
    },
    {
      title: "已中止",
      taskStates: [JobJobStateEnum.Suspended],
      color: STATUS_COLORS.warning,
    },
  ];

  const columns = [
    {
      title: "知识",
      dataIndex: "path",
      width: 250,
      showMultilineEllipsis: true,
      render: (path: string) => {
        return <span className="text-ellipsis">{path}</span>;
      },
    },
    {
      title: "大小",
      dataIndex: "size",
      width: 110,
      render: (text: number) => {
        return FileUtils.formatFileSize(text);
      },
    },
    {
      title: "解析状态",
      dataIndex: "state",
      width: 120,
      render: (text: string, record: any) => {
        console.log("text", text);
        const statusConfig = FileStates.find((item) => item.id === text);
        return (
          <StatusTag
            statusConfig={statusConfig}
            tips={{
              show:
                FailedFileStates.includes(text) &&
                text !== DocumentInfoDocumentStateEnum.DocumentParsingCancelled,
              content: (
                <span style={{ wordBreak: "keep-all" }}>
                  {FileErrors?.find((item) => item.id === record.err)?.title}
                </span>
              ),
            }}
          />
        );
      },
    },
  ];

  const getFileList = () => {
    let allFiles: any[] = [];
    // The local file is being uploaded or the file has just been uploaded and the details file has not been obtained yet.
    if (
      isLocalUploading ||
      (localFiles.length > 0 && !detail.fileList?.length)
    ) {
      allFiles = localFiles;
    } else {
      allFiles = detail.fileList || [];
    }

    const tabFiles =
      allFiles.filter((item) => fileStates?.includes(item.state)) || [];
    // Sorting files during import.
    if (tab === FileTabs.RUNNING) {
      const sortOrder = {
        [DocumentInfoDocumentStateEnum.DocumentParsing]: 1,
        [DocumentInfoDocumentStateEnum.DocumentQueued]: 2,
        [DocumentInfoDocumentStateEnum.DocumentCrawlingQueued]: 3,
        [DocumentInfoDocumentStateEnum.DocumentCrawling]: 4,
        unknownState: 999,
      };
      tabFiles.sort((a, b) => {
        return (
          (sortOrder[a.state] ?? sortOrder.unknownState) -
          (sortOrder[b.state] ?? sortOrder.unknownState)
        );
      });
    }

    return { tabFiles, allFiles };
  };
  const { tabFiles, allFiles } = getFileList();

  // 根据文件状态决定使用导入还是解析术语
  const getProgressLabels = () => {
    // 如果所有文件都在解析中，使用解析术语
    const allParsing =
      tabFiles.length > 0 &&
      tabFiles.every(
        (file) => file.state === DocumentInfoDocumentStateEnum.DocumentParsing,
      );

    // 如果有任何文件在导入中，使用导入术语
    const hasImporting = tabFiles.some(
      (file) => file.state === DocumentInfoDocumentStateEnum.DocumentQueued,
    );

    if (allParsing) {
      return {
        progress: "解析进度",
        size: "已解析大小",
        count: "已解析数量",
      };
    }

    if (hasImporting) {
      return {
        progress: "导入进度",
        size: "已导入大小",
        count: "已导入数量",
      };
    }

    // 默认使用导入术语
    return {
      progress: "导入进度",
      size: "已导入大小",
      count: "已导入数量",
    };
  };

  const getFileStats = () => {
    if (isLocalUploading) {
      return localFiles.reduce(
        (prev, cur) => {
          if (cur.isChunk) {
            return prev;
          }
          // Upload successful.
          if (cur.state === DocumentInfoDocumentStateEnum.DocumentQueued) {
            prev.successCount += 1;
            prev.successSize += cur.size;
          }
          if (cur.state === DocumentInfoDocumentStateEnum.DocumentFailed) {
            prev.failedCount += 1;
            prev.failedSize += cur.size;
          }
          return prev;
        },
        {
          successCount: 0,
          successSize: 0,
          failedCount: 0,
          failedSize: 0,
          allCount: localFiles.length,
        },
      );
    }

    return {
      successCount: detail.job_info?.succeed_document_count,
      successSize: detail.job_info?.succeed_document_size,
      failedCount: detail.job_info?.failed_document_count,
      failedSize: detail.job_info?.failed_document_size,
      filteredCount: detail.job_info?.filtered_document_count || 0,
      allCount: detail.job_info?.total_document_count,
    };
  };

  const getDetail = () => {
    pollingRef.current.cancel();
    pollingRef.current.start({
      interval: 2 * 1000,
      request: () =>
        JobServiceApi().jobServiceGetJob({ dataset: datasetId, job: jobId }),
      onSuccess: (res) => {
        const data = res?.data || {};
        data.fileList = data.document_info?.map(
          (item: {
            document_error: string;
            display_name: string;
            document_size: number;
            document_state: number;
            document_token: string;
          }) => {
            return {
              err: item.document_error,
              path: item.display_name,
              size: item.document_size,
              state: item.document_state,
              token: item.document_token,
              uid: uuidv4(),
            };
          },
        );
        setDetail(data);

        if (
          isLocalUploading ||
          [
            JobJobStateEnum.Succeeded,
            JobJobStateEnum.Failed,
            JobJobStateEnum.Cancelled,
            JobJobStateEnum.Suspended,
            JobJobStateEnum.PartialSuccess,
          ].includes(data.job_state)
        ) {
          pollingRef.current.cancel();
        }
        // 只有在没有指定defaultTab时才自动设置标签页
        if (!defaultTab) {
          if (data.job_state === JobJobStateEnum.Succeeded) {
            setTab(FileTabs.SUCCESS);
          }
          if (
            [
              JobJobStateEnum.Failed,
              JobJobStateEnum.Suspended,
              JobJobStateEnum.PartialSuccess,
            ].includes(data.job_state)
          ) {
            setTab(FileTabs.FAILED);
          }
        }
      },
      onError: (err) => {
        console.error(err);
        message.destroy();
      },
    });
  };

  const handleCancel = () => {
    Modal.confirm({
      title: "取消导入任务确认",
      content: (
        <>
          <div>{"是否取消该导入任务？\n操作一旦确认无法撤回"}</div>
        </>
      ),

      onOk() {
        // TODO: Replace with actual request to cancel import task.
        // return cancelImportTask({ datasetId, jobId })
        //   .then(() => {
        //     message.success(getCombinedMessage([{ id: 'common.cancel' }, { id: 'common.success' }]))
        //     batchUpload.cancelUpload(jobId)
        //     onBack()
        //   })
        //   .catch((err) => {
        //     console.error(err)
        //   })
      },
    });
  };

  const renderTaskStatus = () => {
    if (detail.job_state === JobJobStateEnum.Parsing) {
      const percent =
        fileStats.allCount > 0
          ? Math.floor((fileStats.successCount / fileStats.allCount) * 100)
          : 0;
      return (
        <div className="taskProgress">
          <Progress percent={percent} />
          {/* TODO: 这期临时去掉取消任务功能，下期再加*/}
          {/* <Button type='warning' onClick={handleCancel}>
            取消任务
          </Button> */}
        </div>
      );
    }

    const failedFile = allFiles.find((item) =>
      FailedFileStates.includes(item.state),
    );
    const errMsg =
      detail.err_msg ||
      FileErrors?.find((item) => item.id === failedFile?.err)?.title;

    if (partSuccess) {
      return (
        <StatusTag
          statusConfig={{ title: "部分解析失败", color: STATUS_COLORS.warning }}
          tips={{
            show: true,
            content: errMsg,
          }}
        />
      );
    }

    const statusConfig = TaskStates.find((item) =>
      item.taskStates.includes(detail.job_state),
    );
    return (
      <StatusTag
        statusConfig={statusConfig}
        tips={{
          show: detail.job_state === JobJobStateEnum.Failed,
          content: errMsg,
        }}
      />
    );
  };

  const handleTableChange = (page: number) => {
    setPage(page);
  };

  useEffect(() => {
    getDetail();
  }, [isLocalUploading]);

  useEffect(() => {
    return () => {
      pollingRef.current.cancel();
    };
  }, []);

  const fileStats = getFileStats();

  return (
    <div className="taskDetail">
      <div className="header">
        <ArrowLeftOutlined className="backIcon" onClick={onBack} />
        <span className="title">
          {getProgressLabels().progress.replace("进度", "任务详情")}
        </span>
        <CloseOutlined onClick={onClose} className="closeIcon" />
      </div>
      <Form className="taskInfo" size="small" labelAlign="left">
        <DetailItem label="创建时间">
          {moment(detail.create_time).format(TIME_FORMAT)}
        </DetailItem>
        <DetailItem label="创建人">{detail.creator}</DetailItem>
        <DetailItem label="已用时">
          <ElapsedTime
            startTime={detail.start_time || detail.create_time || ""}
            endTime={isRunning ? undefined : detail.finish_time}
          />
        </DetailItem>
        <DetailItem label="数据来源">本地文件</DetailItem>
        {isLocalUploading && (
          <>
            <DetailItem label="导入进度">{renderTaskStatus()}</DetailItem>
            <DetailItem label="已导入大小">
              {FileUtils.formatFileSize(fileStats.successSize)}
            </DetailItem>
            <DetailItem label="已导入数量">{fileStats.successCount}</DetailItem>
          </>
        )}
        {!isLocalUploading && (
          <DetailItem label={getProgressLabels().progress}>
            {renderTaskStatus()}
          </DetailItem>
        )}
        {!isLocalUploading &&
          ![JobJobStateEnum.Failed, JobJobStateEnum.Suspended].includes(
            detail.job_state,
          ) && (
            <>
              <DetailItem label={getProgressLabels().size}>
                {FileUtils.formatFileSize(fileStats.successSize)}
              </DetailItem>
              <DetailItem label={getProgressLabels().count}>
                {fileStats.successCount}
              </DetailItem>
            </>
          )}
        {(partSuccess || detail.job_state === JobJobStateEnum.Failed) && (
          <>
            <DetailItem label="已失败大小">
              {FileUtils.formatFileSize(fileStats.failedSize)}
            </DetailItem>
            <DetailItem label="已失败数量">{fileStats.failedCount}</DetailItem>
          </>
        )}
        {fileStats.filteredCount > 0 && (
          <DetailItem label="已过滤的文件数量">
            {fileStats.filteredCount}
          </DetailItem>
        )}
      </Form>
      {(partSuccess || isRunning) && (
        <Radio.Group
          className="tab"
          value={tab}
          onChange={(e) => {
            setTab(e.target.value);
            setPage(1);
          }}
        >
          {isRunning && (
            <Radio.Button value={FileTabs.RUNNING}>导入中</Radio.Button>
          )}
          <Radio.Button value={FileTabs.SUCCESS}>导入成功</Radio.Button>
          <Radio.Button value={FileTabs.FAILED}>导入失败</Radio.Button>
        </Radio.Group>
      )}
      <Table
        columns={columns}
        dataSource={tabFiles}
        rowKey="uid"
        pagination={{
          current: page,
          pageSize: TABLE_PAGE_SIZE,
          total: tabFiles.length,
          hideOnSinglePage: true,
          showSizeChanger: false,
          onChange: handleTableChange,
        }}
      />
    </div>
  );
};

export default ImportTaskDetail;

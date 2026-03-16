import { message, Modal, Radio, Table, Tooltip } from "antd";
import { CloseOutlined } from "@ant-design/icons";
import { useEffect, useRef, useState } from "react";
import moment from "moment";

import {
  RUNNING_TASK_STATES,
  FileTabs,
} from "@/modules/knowledge/constants/common";
import UIUtils from "@/modules/knowledge/utils/ui";
import ElapsedTime from "../ElapsedTime";
import ImportTaskDetail from "../ImportTaskDetail";
import "./index.scss";
import Polling from "@/modules/knowledge/utils/polling";
import { JobServiceApi } from "@/modules/knowledge/utils/request";
import { JobJobStateEnum } from "@/api/generated/knowledge-client";
import { useDatasetPermissionStore } from "@/modules/knowledge/store/dataset_permission";

interface IProps {
  datasetId: string;
  onClose: () => void;
  onSuspendSuccess?: () => void;
}

// 任务状态tab
export enum TaskTab {
  Running = "1",
  Successed = "2",
  Failed = "3",
}

export const TaskTabInfo = [
  {
    id: TaskTab.Running,
    title: "解析中",
    taskStates: [JobJobStateEnum.Creating, JobJobStateEnum.Parsing],
  },
  {
    id: TaskTab.Successed,
    title: "导入成功",
    taskStates: [JobJobStateEnum.Succeeded],
  },
  {
    id: TaskTab.Failed,
    title: "导入失败",
    taskStates: [
      JobJobStateEnum.Cancelled,
      JobJobStateEnum.StageUnspecified,
      JobJobStateEnum.Failed,
      JobJobStateEnum.Suspended,
      JobJobStateEnum.PartialSuccess,
    ],
  },
];

const ImportTaskList = (props: IProps) => {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [total, setTotal] = useState(0);
  const [dataSource, setDataSource] = useState([]);
  const [tab, setTab] = useState(TaskTab.Running);
  const [selectData, setSelectData] = useState(undefined);
  const [showDetail, setShowDetail] = useState(false);
  const pollingRef = useRef(new Polling());
  const { datasetId, onClose, onSuspendSuccess } = props;
  // 读权限
  const hasOnlyReadPermission = useDatasetPermissionStore((state) =>
    state.hasOnlyReadPermission(),
  );
  // 上传权限
  const hasUploadPermission = useDatasetPermissionStore((state) =>
    state.hasUploadPermission(),
  );
  // 写权限
  const hasWritePermission = useDatasetPermissionStore((state) =>
    state.hasWritePermission(),
  );
  // 是否只有读权限
  const isOnlyRead =
    (hasOnlyReadPermission || hasUploadPermission) && !hasWritePermission;

  const getTableData = (params?: {
    page?: number;
    size?: number;
    currentTab?: TaskTab;
  }) => {
    const { page = 1, size = pageSize, currentTab = tab } = params || {};
    setPage(page);
    setPageSize(size);
    pollingRef.current.cancel();
    pollingRef.current.start({
      interval: 10 * 1000,
      request: () =>
        JobServiceApi().jobServiceSearchJobs({
          dataset: datasetId,
          searchJobsRequest: {
            parent: `datasets/{${datasetId}}`,
            jobStatus: TaskTabInfo.find((item) => item.id === currentTab)
              ?.taskStates,
            pageToken: UIUtils.generatePageToken({
              page: page - 1,
              pageSize: size,
              total,
            }),
            pageSize: size,
          },
        }),
      onSuccess: ({ data = {} }) => {
        setTotal(data.total_size || 0);
        setDataSource(data.jobs || []);
      },
      onError: (err) => {
        console.error(err);
        setTotal(0);
        setDataSource([]);
      },
    });
  };

  const changeTab = (v: TaskTab) => {
    setDataSource([]);
    setTab(v);
    getTableData({ currentTab: v });
  };

  function suspendTaskFn(cvm: any) {
    JobServiceApi()
      .jobServiceSuspendJob({
        dataset: datasetId,
        job: cvm?.job_id,
        suspendJobRequest: { name: cvm?.name },
      })
      .then((res) => {
        message.success("中止任务成功");
        onSuspendSuccess?.(); // 通知父组件标记中止成功
        getTableData({ currentTab: tab });
      });
  }

  function resumeTaskFn(cvm: any) {
    JobServiceApi()
      .jobServiceResumeJob({
        dataset: datasetId,
        job: cvm?.job_id,
        resumeJobRequest: { name: cvm?.name },
      })
      .then((res) => {
        message.success("重试任务成功");
        getTableData({ currentTab: tab });
      });
  }

  function deleteTaskFn(cvm: any) {
    JobServiceApi()
      .jobServiceDeleteJob({ dataset: datasetId, job: cvm?.job_id })
      .then((res) => {
        message.success("删除任务成功");
        getTableData({ currentTab: tab });
      });
  }

  function confirmDelete(cvm: any) {
    Modal.confirm({
      title: "确认删除",
      content: "确定要删除该任务吗？删除后将无法恢复。",
      okText: "确认",
      cancelText: "取消",
      onOk: () => {
        deleteTaskFn(cvm);
      },
    });
  }

  const columns = [
    {
      title: "创建时间",
      dataIndex: "create_time",
      width: 200,
      render: (text: number) => {
        return moment(text).format("YYYY-MM-DD HH:mm:ss");
      },
    },
    {
      title: "名称",
      dataIndex: "display_name",
      width: 200,
      render: (text: string) => {
        return (
          <Tooltip title={text}>
            <div className="ellipsis-text">{text || "导入中..."}</div>
          </Tooltip>
        );
      },
    },
    {
      title: "创建人",
      dataIndex: "creator",
      width: 120,
    },
    {
      title: "数据来源",
      dataIndex: "data_source_type",
      width: 115,
      render: (type: number) => {
        return "本地文件";
      },
    },
    {
      title: "已用时",
      dataIndex: "create_time",
      width: 105,
      render: (time: string, record: any) => {
        return (
          <ElapsedTime
            startTime={record.start_time || time}
            endTime={
              RUNNING_TASK_STATES.includes(record.job_state)
                ? undefined
                : record.finish_time
            }
          />
        );
      },
    },
    {
      title: "操作",
      key: "action",
      width: 140,
      render: (record: any) => {
        return (
          <>
            <a
              onClick={() => {
                setSelectData(record);
                setShowDetail(true);
                pollingRef.current.cancel();
              }}
              style={{ marginRight: 6 }}
            >
              查看
            </a>
            {tab === TaskTab.Running && !isOnlyRead && (
              <a onClick={() => suspendTaskFn(record)}>中止</a>
            )}
            {tab === TaskTab.Failed && !isOnlyRead && (
              <a
                style={{ marginRight: 6 }}
                onClick={() => resumeTaskFn(record)}
              >
                重试
              </a>
            )}
            {tab === TaskTab.Failed && !isOnlyRead && (
              <a onClick={() => confirmDelete(record)}>删除</a>
            )}
          </>
        );
      },
    },
  ];

  useEffect(() => {
    getTableData();
    return () => {
      pollingRef.current.cancel();
    };
  }, []);

  if (showDetail && selectData) {
    return (
      <ImportTaskDetail
        datasetId={datasetId}
        jobId={selectData.job_id}
        onBack={() => {
          getTableData({ page });
          setSelectData(undefined);
          setShowDetail(false);
        }}
        onClose={onClose}
        defaultTab={tab === TaskTab.Failed ? FileTabs.FAILED : undefined}
      />
    );
  }

  return (
    <div className="import-task-list">
      <div className="header">
        <span className="import-task-list-title">导入数据-解析数据任务</span>
        <CloseOutlined onClick={onClose} className="closeIcon" />
      </div>
      <Radio.Group
        value={tab}
        className="tab"
        onChange={(e) => changeTab(e.target.value)}
      >
        {TaskTabInfo.map((item) => {
          return (
            <Radio.Button value={item.id} key={item.id}>
              {item.title}
            </Radio.Button>
          );
        })}
      </Radio.Group>
      <Table
        columns={columns}
        dataSource={dataSource}
        rowKey="jobId"
        pagination={{
          current: page,
          pageSize,
          total,
        }}
        onChange={(pagination) => {
          getTableData({ page: pagination.current, size: pagination.pageSize });
        }}
      />
    </div>
  );
};

export default ImportTaskList;

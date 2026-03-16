import {
  message,
  Button,
  Badge,
  Dropdown,
  Menu,
  Tooltip,
  Input,
  Tag,
} from "antd";
import type { MenuProps } from "antd";
import { useEffect, useRef, useState, useCallback } from "react";
import { useParams } from "react-router-dom";
import {
  EditOutlined,
  SettingOutlined,
  DeleteOutlined,
  CopyOutlined,
  DownOutlined,
} from "@ant-design/icons";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  Dataset,
  DatasetAclEnum,
  DocTypeEnum,
} from "@/api/generated/knowledge-client";

import { RUNNING_TASK_STATES } from "@/modules/knowledge/constants/common";
import RenameModel, {
  RenameFormItem,
  RenameModalRef,
} from "@/modules/knowledge/components/RenameModel";
import KnowledgeTable, {
  IKnowledgeListRef,
  TreeNode,
} from "./components/KnowledgeTable";
import ImportKnowledgeModal, {
  IImportKnowledgeModalRef,
} from "./components/ImportKnowledgeModal";
import ImportTaskManage, {
  IImportTaskManageRef,
} from "./components/ImportTaskManage";
import Polling from "@/modules/knowledge/utils/polling";
import TreeUtils from "@/modules/knowledge/utils/tree";
import ConfirmModal, {
  ConfirmImperativeProps,
} from "@/modules/knowledge/components/ConfirmModal";
import CreateUpdateModal, {
  UpdateImperativeProps,
} from "@/modules/knowledge/components/UpdateModal";
import { KnowledgeBaseServiceApi } from "@/modules/knowledge/utils/request";
import { DocumentServiceApi, JobServiceApi } from "../../utils/request";
import { useDatasetPermissionStore } from "@/modules/knowledge/store/dataset_permission";

import { DetailPageHeader } from "@/components/ui";

import "./index.scss";

const { Search } = Input;

const Detail = () => {
  const knowledgeListRef = useRef<IKnowledgeListRef>(null);
  const createFolderRef = useRef<RenameModalRef>(null);
  const importKnowledgeRef = useRef<IImportKnowledgeModalRef>();
  const importTaskRef = useRef<IImportTaskManageRef>();
  const pollingRef = useRef(new Polling());
  const importingTaskListRef = useRef([]);
  const confirmRef = useRef<ConfirmImperativeProps>(null);
  const createUpdateRef = useRef<UpdateImperativeProps>(null);

  const [detail, setDetail] = useState<Dataset>();
  const [importingTotal, setImportingTotal] = useState(0);

  const { id = "" } = useParams();

  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // 使用权限 store
  const { setCurrentDataset, clearDataset } = useDatasetPermissionStore();

  const getDetail = useCallback(() => {
    KnowledgeBaseServiceApi()
      .datasetServiceGetDataset({ dataset: id })
      .then((res) => {
        setDetail(res.data);
        // 更新权限 store
        setCurrentDataset(res.data);
      });
  }, [id, setCurrentDataset]);

  useEffect(() => {
    getDetail();
    getImportingTotal();

    return () => {
      pollingRef.current.cancel();
      // 组件卸载时清除权限信息
      clearDataset();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [getDetail, clearDataset]);

  function getImportingTotal() {
    pollingRef.current.cancel();
    pollingRef.current.start({
      interval: 10 * 1000,
      request: () =>
        JobServiceApi().jobServiceSearchJobs({
          dataset: id,
          searchJobsRequest: {
            parent: `datasets/{${id}}`,
            job_status: RUNNING_TASK_STATES,
          },
        }),
      onSuccess: ({ data = {} }) => {
        const newTaskList = data.jobs || [];
        if (newTaskList.length === 0) {
          pollingRef.current.cancel();
        }
        compareTaskChange(newTaskList, importingTaskListRef.current);
        setImportingTotal(data.total_size || 0);
        importingTaskListRef.current = newTaskList;
      },
    });
  }

  function compareTaskChange(newTaskList: any[], prevTaskList: any[]) {
    const completeTasks = prevTaskList.filter(
      (item) => !newTaskList.some((i) => item.job_id === i.job_id),
    );
    if (!completeTasks.length) {
      return;
    }

    // Update document count.
    if (completeTasks.length > 0) {
      getDetail();
    }

    // There are multiple tasks to complete or the root node needs to be updated.
    if (
      completeTasks.length > 1 ||
      completeTasks.find((item) => !item.document_pid)
    ) {
      knowledgeListRef.current?.getTableData();
      return;
    }

    // Only one task is completed to update the parent node and child node.
    const task = completeTasks[0];
    const parentNode: TreeNode | undefined = TreeUtils.findNode(
      knowledgeListRef.current?.treeData || [],
      (node: TreeNode) => {
        return node.document_id === task.document_pid;
      },
    );
    if (!parentNode) {
      return;
    }
    if (parentNode?.loaded) {
      knowledgeListRef.current!.getTableData({
        pId: parentNode.document_id ?? "",
        level: parentNode.level + 1,
        parentNode: { ...parentNode, loaded: false },
      });
      return;
    }
    knowledgeListRef.current!.updateDocument({
      documentId: parentNode.document_id ?? "",
    });
  }

  function openImportModal(data?: any) {
    const modalData = { ...detail, ...data };
    importKnowledgeRef.current?.handleOpen(modalData);
  }

  function onCreateFolder(data: RenameFormItem) {
    DocumentServiceApi()
      .documentServiceCreateDocument({
        dataset: id,
        doc: {
          display_name: data.name,
          name: data.name,
          type: DocTypeEnum.Folder,
        },
      })
      .then(() => {
        message.success("创建文件夹成功");
        knowledgeListRef.current?.getTableData();
      });
  }

  function onUpdate(data: Dataset): Promise<void> {
    return KnowledgeBaseServiceApi()
      .datasetServiceUpdateDataset({
        dataset: data.dataset_id || "",
        dataset2: data,
      })
      .then(() => {
        message.success("编辑知识库成功");
        getDetail();
      });
  }

  function onDelete(knowledgeBaseId: string) {
    KnowledgeBaseServiceApi()
      .datasetServiceDeleteDataset({ dataset: knowledgeBaseId })
      .then(() => {
        message.success("删除知识库成功！");
        navigate({
          pathname: "/list",
        });
      });
  }

  function onSearch(value: string) {
    knowledgeListRef.current?.refresh(value);
  }

  // 写权限
  const hasWritePermission = useDatasetPermissionStore((state) =>
    state.hasWritePermission(),
  );

  // 上传权限
  const hasUploadPermission = useDatasetPermissionStore((state) =>
    state.hasUploadPermission(),
  );
  const canImport = hasUploadPermission || hasWritePermission;

  return (
    <div className="knowledge-container !items-start">
      <DetailPageHeader
        title={detail?.display_name}
        titleExtra={
          <>
            <span
              style={{
                marginRight: "4px",
                color: "var(--color-text-description)",
              }}
            >
              ID: {detail?.dataset_id}
            </span>
            <CopyOutlined
              style={{ color: "var(--color-text-description)" }}
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(detail?.dataset_id || "");
                  message.success("复制成功");
                } catch {
                  message.success("复制失败，请手动复制");
                }
              }}
            />
          </>
        }
        settingsMenu={
          detail?.acl?.includes(DatasetAclEnum.DatasetWrite) && (
            <div>
              <Tooltip title={"编辑"}>
                <Button
                  icon={<EditOutlined />}
                  style={{ marginLeft: "12px", width: "24px", height: "24px" }}
                  onClick={() => {
                    createUpdateRef.current?.onOpen(detail);
                  }}
                />
              </Tooltip>
              <Tooltip title={"授权"}>
                <Button
                  icon={<SettingOutlined />}
                  style={{ marginLeft: "12px", width: "24px", height: "24px" }}
                  onClick={() =>
                    navigate({
                      pathname: `/auth/${id}`,
                    })
                  }
                />
              </Tooltip>
              <Tooltip title={"删除"}>
                <Button
                  icon={<DeleteOutlined />}
                  style={{ marginLeft: "12px", width: "24px", height: "24px" }}
                  onClick={() =>
                    confirmRef.current?.onOpen({
                      id,
                      title: `删除知识库【${detail?.display_name}】`,
                      content:
                        "删除操作一旦确认无法撤回，此知识库相关应用将失效！请输入下述文字进行再次确认：",
                      confirmText: "确认删除此知识库，我已知悉删除后的影响",
                    })
                  }
                />
              </Tooltip>
            </div>
          )
        }
        breadcrumbs={[
          { title: "知识库", href: "/appplatform/lib/knowledge/list" },
          { title: detail?.display_name },
        ]}
        description={detail?.desc}
        extraContent={[
          {
            label: "标签",
            value:
              detail?.tags && detail?.tags.length > 0
                ? detail.tags.map((tag) => (
                    <Tag style={{ marginLeft: "8px" }} key={tag}>
                      {tag}
                    </Tag>
                  ))
                : "-",
          },
        ]}
        onBack={() => {
          const bool = ["aiwrite", "aireview", "chat"].includes(
            searchParams.get("from") ?? "",
          );
          if (bool) {
            navigate("/list");
          } else {
            navigate(-1);
          }
        }}
      />
      <div className="my-4 mt-6 w-full">
        <Search
          className="search-input"
          placeholder="搜索文档名称、标签、更新人"
          allowClear
          variant="borderless"
          onSearch={onSearch}
          style={{
            width: 300,
            marginRight: "10px",
          }}
        />
        {canImport && (
          <>
            {hasWritePermission && (
              <Button
                color="primary"
                variant="outlined"
                className="mx-4"
                ghost
                onClick={() => {
                  createFolderRef.current?.onOpen({
                    title: "创建文件夹",
                    form: {
                      name: "文件夹名称",
                      namePlaceholder:
                        "仅支持中英文、数字、下划线，长度不超过30个字符",
                      nameLen: 30,
                      nameRules: [
                        {
                          required: true,
                          validator: (_: any, value: string) => {
                            if (!value) {
                              return Promise.reject("请输入文件夹名称");
                            }
                            if (
                              !/^[a-zA-Z\d\u4e00-\u9fa5_]+$/.test(value) ||
                              value.length > 30
                            ) {
                              return Promise.reject(
                                "仅支持中英文、数字、下划线，长度不超过30个字符",
                              );
                            }
                            return Promise.resolve();
                          },
                        },
                      ],
                    },
                    data: {
                      name: "",
                    },
                  });
                }}
              >
                创建文件夹
              </Button>
            )}
            <Badge count={importingTotal} size="small" style={{ zIndex: 2 }}>
              <Button.Group className="button-group">
                <Button
                  type="primary"
                  onClick={() => openImportModal({ importMode: "file" })}
                >
                  导入文件
                </Button>
                <Dropdown
                  overlay={
                    <Menu>
                      <Menu.Item
                        key="importFile"
                        onClick={() => {
                          openImportModal({ importMode: "file" });
                        }}
                      >
                        导入文件
                      </Menu.Item>
                      <Menu.Item
                        key="importFolder"
                        onClick={() => {
                          openImportModal({
                            selectDirectory: true,
                            importMode: "folder",
                          });
                        }}
                      >
                        导入文件夹
                      </Menu.Item>
                      <Menu.Item
                        key="importZip"
                        onClick={() => {
                          openImportModal({ importMode: "zip" });
                        }}
                      >
                        导入压缩包
                      </Menu.Item>
                      <Menu.Item
                        key="taskManage"
                        onClick={() => {
                          importTaskRef.current?.handleOpen(detail);
                        }}
                      >
                        解析任务管理
                        {importingTotal > 0 && (
                          <Badge
                            count={importingTotal}
                            size="small"
                            offset={[-4, 6]}
                          >
                            <span
                              style={{
                                marginLeft: importingTotal >= 10 ? 6 : 12,
                                opacity: 0,
                              }}
                            >
                              {importingTotal}
                            </span>
                          </Badge>
                        )}
                      </Menu.Item>
                    </Menu>
                  }
                >
                  <Button type="primary">
                    <DownOutlined />
                  </Button>
                </Dropdown>
              </Button.Group>
            </Badge>
            {hasWritePermission && (
              <Dropdown
                menu={{
                  items: [
                    {
                      key: "batchMove",
                      label: "批量移动",
                      onClick: () => {
                        knowledgeListRef.current?.openBatchMove?.();
                      },
                    },
                    {
                      key: "batchDelete",
                      label: "批量删除",
                      onClick: () => {
                        knowledgeListRef.current?.deleteKnowledge();
                      },
                    },
                    {
                      key: "batchReparse",
                      label: "批量重解析",
                      onClick: () => {
                        knowledgeListRef.current?.restartCheckedKnowledge();
                      },
                    },
                    {
                      key: "batchEditTags",
                      label: "批量编辑标签",
                      onClick: () => {
                        knowledgeListRef.current?.openBatchEditTags?.();
                      },
                    },
                  ] as MenuProps["items"],
                }}
                trigger={["click"]}
              >
                <Button.Group
                  className="button-group"
                  style={{ marginLeft: "16px" }}
                >
                  <Button variant="outlined" color="primary" ghost>
                    批量操作
                  </Button>
                  <Button variant="outlined" color="primary" ghost>
                    <DownOutlined />
                  </Button>
                </Button.Group>
              </Dropdown>
            )}
          </>
        )}
      </div>
      {detail && (
        <KnowledgeTable
          ref={knowledgeListRef}
          detail={detail}
          onImportKnowledge={(data) => openImportModal(data)}
          getImportingTotal={getImportingTotal}
          getDetail={getDetail}
        />
      )}

      <ConfirmModal ref={confirmRef} onClick={onDelete} />

      <CreateUpdateModal ref={createUpdateRef} onUpdate={onUpdate} />

      <RenameModel
        ref={createFolderRef}
        onSubmit={async (data) => onCreateFolder(data)}
      />

      <ImportKnowledgeModal
        ref={importKnowledgeRef}
        onOk={() => {
          getImportingTotal();
        }}
      />

      <ImportTaskManage
        ref={importTaskRef}
        onClose={(hasSuspended) => {
          if (hasSuspended) {
            // 中止成功后，先清空任务列表缓存，避免 compareTaskChange 触发额外的刷新
            importingTaskListRef.current = [];
            // 刷新导入任务数量
            getImportingTotal();
            // 刷新文档列表（p_id 为空，刷新根目录）
            knowledgeListRef.current?.getTableData({ pId: "", level: 0 });
          } else {
            getImportingTotal();
          }
        }}
      />
    </div>
  );
};

export default Detail;

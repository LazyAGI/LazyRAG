import {
  message,
  Button,
  Badge,
  Dropdown,
  Tooltip,
  Input,
  Tag,
  Space,
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
import { useTranslation } from "react-i18next";
import {
  Dataset,
  DatasetAclEnum,
  DocTypeEnum,
} from "@/api/generated/knowledge-client";

import Polling from "@/modules/knowledge/utils/polling";
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
import TreeUtils from "@/modules/knowledge/utils/tree";
import ConfirmModal, {
  ConfirmImperativeProps,
} from "@/modules/knowledge/components/ConfirmModal";
import CreateUpdateModal, {
  UpdateImperativeProps,
} from "@/modules/knowledge/components/UpdateModal";
import { KnowledgeBaseServiceApi } from "@/modules/knowledge/utils/request";
import { DocumentServiceApi, TaskServiceApi } from "../../utils/request";
import { useDatasetPermissionStore } from "@/modules/knowledge/store/dataset_permission";

import { DetailPageHeader } from "@/components/ui";

import "./index.scss";

const { Search } = Input;

const Detail = () => {
  const { t } = useTranslation();
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

  const { setCurrentDataset, clearDataset } = useDatasetPermissionStore();

  const getDetail = useCallback(() => {
    KnowledgeBaseServiceApi()
      .datasetServiceGetDataset({ dataset: id })
      .then((res) => {
        setDetail(res.data);
        setCurrentDataset(res.data);
      });
  }, [id, setCurrentDataset]);

  useEffect(() => {
    console.log("searchParams", searchParams);
    getDetail();
    getImportingTotal();

    return () => {
      pollingRef.current.cancel();
      clearDataset();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [getDetail, clearDataset]);

  function getImportingTotal() {
    pollingRef.current.cancel();
    pollingRef.current.start({
      interval: 10 * 1000,
      request: () => TaskServiceApi().listTasks(id),
      onSuccess: ({ data = {} }) => {
        const RUNNING_STATES = ["WAITING", "WORKING"];
        const allTasks = data.tasks || [];
        const newTaskList = allTasks.filter((t: any) =>
          RUNNING_STATES.includes(t.task_state),
        );
        if (newTaskList.length === 0) {
          pollingRef.current.cancel();
        }
        compareTaskChange(newTaskList, importingTaskListRef.current);
        setImportingTotal(newTaskList.length);
        importingTaskListRef.current = newTaskList;
      },
    });
  }

  function compareTaskChange(newTaskList: any[], prevTaskList: any[]) {
    const completeTasks = prevTaskList.filter(
      (item) => !newTaskList.some((i) => item.task_id === i.task_id),
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
      completeTasks.find((item) => !item.target_pid)
    ) {
      knowledgeListRef.current?.getTableData();
      return;
    }

    // Only one task is completed to update the parent node and child node.
    const task = completeTasks[0];
    const parentNode: TreeNode | undefined = TreeUtils.findNode(
      knowledgeListRef.current?.treeData || [],
      (node: TreeNode) => {
        return node.document_id === task.target_pid;
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
        message.success(t("knowledge.createFolderSuccess"));
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
        message.success(t("knowledge.editSuccess"));
        getDetail();
      });
  }

  function onDelete(knowledgeBaseId: string) {
    KnowledgeBaseServiceApi()
      .datasetServiceDeleteDataset({ dataset: knowledgeBaseId })
      .then(() => {
        message.success(t("knowledge.deleteSuccess"));
        navigate({
          pathname: "/list",
        });
      });
  }

  function onSearch(value: string) {
    knowledgeListRef.current?.refresh(value);
  }

  const hasWritePermission = useDatasetPermissionStore((state) =>
    state.hasWritePermission(),
  );

  const hasUploadPermission = useDatasetPermissionStore((state) =>
    state.hasUploadPermission(),
  );
  const canImport = hasUploadPermission || hasWritePermission;

  return (
    <div
      className="knowledge-detail-page"
      style={{
        width: "100%",
        minWidth: 0,
        display: "flex",
        flexDirection: "column",
        paddingBottom: "24px",
      }}
    >
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
                  message.success(t("knowledge.copySuccess"));
                } catch {
                  message.error(t("knowledge.copyFailedManual"));
                }
              }}
            />
          </>
        }
        settingsMenu={
          detail?.acl?.includes(DatasetAclEnum.DatasetWrite) && (
            <div>
              <Tooltip title={t("common.edit")}>
                <Button
                  icon={<EditOutlined />}
                  style={{ marginLeft: "12px", width: "24px", height: "24px" }}
                  onClick={() => {
                    createUpdateRef.current?.onOpen(detail);
                  }}
                />
              </Tooltip>
              <Tooltip title={t("knowledge.authorize")}>
                <Button
                  icon={<SettingOutlined />}
                  style={{ marginLeft: "12px", width: "24px", height: "24px" }}
                  onClick={() =>
                    navigate({
                      pathname: `/lib/knowledge/auth/${id}`,
                    })
                  }
                />
              </Tooltip>
              <Tooltip title={t("common.delete")}>
                <Button
                  icon={<DeleteOutlined />}
                  style={{ marginLeft: "12px", width: "24px", height: "24px" }}
                  onClick={() =>
                    confirmRef.current?.onOpen({
                      id,
                      title: t("knowledge.deleteTitle", {
                        name: detail?.display_name,
                      }),
                      content: t("knowledge.deleteContent"),
                      confirmText: t("knowledge.deleteConfirmText"),
                    })
                  }
                />
              </Tooltip>
            </div>
          )
        }
        breadcrumbs={[
          { title: t("layout.knowledgeBase"), href: "/appplatform/lib/knowledge/list" },
          { title: detail?.display_name },
        ]}
        description={detail?.desc}
        extraContent={[
          {
            label: t("knowledge.tags"),
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
      <div className="toolbar my-4 mt-6 w-full">
        <Search
          className="search-input"
          placeholder={t("knowledge.searchDocPlaceholder")}
          allowClear
          variant="borderless"
          onSearch={onSearch}
          style={{
            width: 300,
          }}
        />
        {canImport && (
          <div className="toolbar-actions">
            {hasWritePermission && (
              <Button
                color="primary"
                variant="outlined"
                ghost
                onClick={() => {
                  createFolderRef.current?.onOpen({
                    title: t("knowledge.createFolder"),
                    form: {
                      name: t("knowledge.folderName"),
                      namePlaceholder: t("knowledge.folderNameRule"),
                      nameLen: 30,
                      nameRules: [
                        {
                          required: true,
                          validator: (_: any, value: string) => {
                            if (!value) {
                              return Promise.reject(t("knowledge.inputFolderName"));
                            }
                            if (
                              !/^[a-zA-Z\d\u4e00-\u9fa5_]+$/.test(value) ||
                              value.length > 30
                            ) {
                              return Promise.reject(
                                t("knowledge.folderNameRule"),
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
                {t("knowledge.createFolder")}
              </Button>
            )}
            <Badge count={importingTotal} size="small" style={{ zIndex: 2 }}>
              <Space.Compact>
                <Button
                  type="primary"
                  onClick={() => openImportModal({ importMode: "file" })}
                >
                  {t("knowledge.importFile")}
                </Button>
                <Dropdown
                  menu={{
                    items: [
                      {
                        key: "importFile",
                        label: t("knowledge.importFile"),
                      },
                      {
                        key: "importFolder",
                        label: t("knowledge.importFolder"),
                      },
                      {
                        key: "importZip",
                        label: t("knowledge.importZip"),
                      },
                      {
                        key: "taskManage",
                        label: (
                          <>
                            {t("knowledge.taskManageParse")}
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
                          </>
                        ),
                      },
                    ],
                    onClick: ({ key }) => {
                      if (key === "importFile") {
                        openImportModal({ importMode: "file" });
                        return;
                      }

                      if (key === "importFolder") {
                        openImportModal({
                          selectDirectory: true,
                          importMode: "folder",
                        });
                        return;
                      }

                      if (key === "importZip") {
                        openImportModal({ importMode: "zip" });
                        return;
                      }

                      if (key === "taskManage") {
                        importTaskRef.current?.handleOpen(detail);
                      }
                    },
                  }}
                >
                  <span style={{ display: "inline-flex" }}>
                    <Button type="primary">
                      <DownOutlined />
                    </Button>
                  </span>
                </Dropdown>
              </Space.Compact>
            </Badge>
            {hasWritePermission && (
              <Dropdown
                menu={{
                  items: [
                    {
                      key: "batchMove",
                      label: t("knowledge.batchMove"),
                      onClick: () => {
                        knowledgeListRef.current?.openBatchMove?.();
                      },
                    },
                    {
                      key: "batchDelete",
                      label: t("knowledge.batchDelete"),
                      onClick: () => {
                        knowledgeListRef.current?.deleteKnowledge();
                      },
                    },
                    {
                      key: "batchReparse",
                      label: t("knowledge.batchReparse"),
                      onClick: () => {
                        knowledgeListRef.current?.restartCheckedKnowledge();
                      },
                    },
                    {
                      key: "batchEditTags",
                      label: t("knowledge.batchEditTags"),
                      onClick: () => {
                        knowledgeListRef.current?.openBatchEditTags?.();
                      },
                    },
                  ] as MenuProps["items"],
                }}
                trigger={["click"]}
              >
                <span style={{ display: "inline-flex" }}>
                  <Space.Compact>
                    <Button variant="outlined" color="primary" ghost>
                      {t("knowledge.batchActions")}
                    </Button>
                    <Button variant="outlined" color="primary" ghost>
                      <DownOutlined />
                    </Button>
                  </Space.Compact>
                </span>
              </Dropdown>
            )}
          </div>
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
            importingTaskListRef.current = [];
            getImportingTotal();
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

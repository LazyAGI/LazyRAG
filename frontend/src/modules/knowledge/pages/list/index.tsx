import { FC, useState, useEffect, useRef } from "react";
import {
  Button,
  Form,
  Tooltip,
  Flex,
  message,
  TablePaginationConfig,
  Select,
  Tag,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useNavigate } from "react-router-dom";
import moment from "moment";
import { EditFilled } from "@ant-design/icons";

import ListPageHeader from "@/modules/knowledge/components/ListPageHeader";
import ConfirmModal, {
  ConfirmImperativeProps,
} from "@/modules/knowledge/components/ConfirmModal";
import CreateUpdateModal, {
  UpdateImperativeProps,
} from "@/modules/knowledge/components/UpdateModal";
import UIUtils from "@/modules/knowledge/utils/ui";
import {
  DocumentServiceApi,
  KnowledgeBaseServiceApi,
} from "@/modules/knowledge/utils/request";
import { ALL_TAGS, TIME_FORMAT } from "@/modules/knowledge/constants/common";
import {
  Dataset,
  DatasetAclEnum,
  DocDocumentStageEnum,
  DocTypeEnum,
} from "@/api/generated/knowledge-client";
import KnowledgeTag from "@/modules/knowledge/components/KnowledgeTag";
import FileUtils from "@/modules/knowledge/utils/file";

import { ListPageTable } from "@/components/ui";
import EditTags from "@/modules/knowledge/pages/detail/components/KnowledgeTable/editTags";
import type { TreeNode } from "@/modules/knowledge/pages/detail/components/KnowledgeTable";

import "./index.scss";

const DocumentStageEnum = {
  [DocDocumentStageEnum.DocumentUploaded]: "未解析",
  [DocDocumentStageEnum.DocumentParsing]: "解析中",
  [DocDocumentStageEnum.DocumentParseSuccessfully]: "已解析",
  [DocDocumentStageEnum.DocumentParsingFailed]: "解析失败",
};

type DocRow = {
  dataset_id?: string;
  document_id?: string;
  display_name?: string;
  rel_path?: string;
  document_stage?: string;
  type?: string;
  document_size?: number | string;
  update_time?: string;
  creator?: string;
  uri?: string;
  data_source_type?: string;
  tags?: string[];
  p_id?: string;
};

const KnowledgePage: FC = () => {
  const [form] = Form.useForm();
  const navigate = useNavigate();

  const confirmRef = useRef<ConfirmImperativeProps>(null);
  const createUpdateRef = useRef<UpdateImperativeProps>(null);

  const [loading, setLoading] = useState(false);
  const [pagination, setPagination] = useState<TablePaginationConfig>({
    current: 1,
    pageSize: 10,
    total: 0,
  });
  const [dataSource, setDataSource] = useState<Dataset[] | undefined>([]);
  const [tags, setTags] = useState<string[]>([]);
  const [knowledgeType, setKnowledgeType] = useState<string>("knowledgeBase");
  const [showTagEditModal, setShowTagEditModal] = useState(false);
  const [tagEditRecord, setTagEditRecord] = useState<DocRow | null>(null);

  useEffect(() => {
    getTags();
    getTableData();
  }, []);

  useEffect(() => {
    // 当 knowledgeType 变化时，重新获取数据
    if (knowledgeType) {
      getTableData(1, pagination.pageSize);
    }
  }, [knowledgeType]);
  const handleOpenTagEdit = (record: DocRow) => {
    setTagEditRecord(record);
    setShowTagEditModal(true);
  };
  const handleCloseTagEdit = () => {
    setShowTagEditModal(false);
    setTagEditRecord(null);
  };
  const handleTagEditSuccess = () => {
    getTableData(pagination.current, pagination.pageSize);
  };

  // 知识库列表
  const columns: ColumnsType<Dataset> = [
    {
      title: "知识库名称/ID",
      dataIndex: "display_name",
      width: 350,
      render: (name: string, data: Dataset) => {
        return (
          <Flex vertical align={"flex-start"}>
            <Button
              className="link-btn"
              type="link"
              style={{ maxWidth: "100%" }}
              onClick={() => {
                navigate({
                  pathname: `/detail/${data.dataset_id}`,
                });
              }}
            >
              <Tooltip title={name}>
                <span className="text-ellipsis">{name}</span>
              </Tooltip>
            </Button>
            <Tooltip title={data.dataset_id}>
              <span
                className="text-ellipsis"
                style={{ color: "var(--color-text-description)" }}
              >
                {data.dataset_id}
              </span>
            </Tooltip>
          </Flex>
        );
      },
    },
    {
      title: "描述",
      dataIndex: "desc",
      ellipsis: {
        showTitle: false,
      },
      width: 200,
      render: (desc: string) => (
        <Tooltip placement="topLeft" title={desc}>
          <span>{desc}</span>
        </Tooltip>
      ),
    },
    {
      title: "标签",
      dataIndex: "tags",
      width: 180,
      render: (knowledgeBaseTags: string[]) => {
        return (
          <Flex style={{ overflowX: "auto", padding: "13px 0" }}>
            {knowledgeBaseTags.map((tag, index) => {
              return <KnowledgeTag key={index} title={tag} checkable={false} />;
            })}
          </Flex>
        );
      },
    },
    {
      title: "更新日期",
      dataIndex: "update_time",
      width: 180,
      render: (time: string) => {
        return moment(time).format("YYYY-MM-DD HH:mm:ss");
      },
    },
    {
      title: "解析大小",
      dataIndex: "document_size",
      width: 100,
      render: (document_size: string) => {
        return FileUtils.formatFileSize(document_size);
      },
    },
    {
      title: "文件数量",
      dataIndex: "document_count",
      width: 100,
    },
    {
      title: "操作",
      key: "action",
      width: 160,
      fixed: "right",
      render: (data: Dataset) => {
        if (!data.acl?.includes(DatasetAclEnum.DatasetWrite)) {
          return null;
        }
        return (
          <Flex gap={10} wrap align="center">
            <Button
              className="link-btn"
              type="link"
              onClick={() => {
                createUpdateRef.current?.onOpen(data);
              }}
            >
              编辑
            </Button>
            <Button
              className="link-btn"
              type="link"
              onClick={() =>
                navigate({
                  pathname: `/auth/${data.dataset_id}`,
                })
              }
            >
              授权
            </Button>
            <Button
              className="link-btn"
              type="link"
              danger
              onClick={() =>
                confirmRef.current?.onOpen({
                  id: data.dataset_id || "",
                  title: `删除知识库【${data.display_name}】`,
                  content:
                    "删除操作一旦确认无法撤回，此知识库相关应用将失效！请输入下述文字进行再次确认：",
                  confirmText: "确认删除此知识库，我已知悉删除后的影响",
                })
              }
            >
              删除
            </Button>
          </Flex>
        );
      },
    },
  ];

  // 知识列表
  const knowledgeColumns: ColumnsType<DocRow> = [
    {
      title: "知识名称",
      dataIndex: "display_name",
      width: 350,
      render: (name: string, record) => {
        return (
          <Flex vertical align={"flex-start"}>
            <Button
              className="link-btn"
              type="link"
              style={{ maxWidth: "100%" }}
              onClick={() => {
                const documentId = record?.document_id;
                const datasetId = record?.dataset_id;
                const relPathtype = record?.type;
                // 如果是文件夹，跳转到知识库详情页
                if (relPathtype === "FOLDER") {
                  navigate({ pathname: `/detail/${datasetId}` });
                } else {
                  navigate({
                    pathname:
                      documentId && datasetId
                        ? `/knowledge/${datasetId}/${documentId}`
                        : `/detail/${datasetId}`,
                  });
                }
              }}
            >
              <Tooltip title={name}>
                <span className="text-ellipsis">{name}</span>
              </Tooltip>
            </Button>
          </Flex>
        );
      },
    },
    {
      title: "标签",
      dataIndex: "tags",
      width: 120,
      render: (rowTags: string[] | undefined, record: DocRow) => {
        if (record.type === DocTypeEnum.Folder) {
          return <span>-</span>;
        }
        if (!rowTags || rowTags.length === 0) {
          return (
            <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
              <span>-</span>
              <Button
                type="text"
                size="small"
                icon={<EditFilled style={{ color: "#1890ff" }} />}
                onClick={(e) => {
                  e.stopPropagation();
                  handleOpenTagEdit(record);
                }}
                style={{ padding: 0, minWidth: "auto", height: "auto" }}
              />
            </div>
          );
        }
        return (
          <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
            <div
              style={{
                display: "flex",
                gap: "4px",
                overflowX: "auto",
                overflowY: "hidden",
                maxWidth: "100%",
                paddingBottom: "2px",
                WebkitOverflowScrolling: "touch",
                flex: 1,
              }}
              className="tags-scroll-container"
            >
              {rowTags.map((tag) => (
                <Tag
                  key={tag}
                  style={{ flexShrink: 0, margin: 0, whiteSpace: "nowrap" }}
                >
                  {tag}
                </Tag>
              ))}
            </div>
            <Button
              type="text"
              size="small"
              icon={<EditFilled style={{ color: "#1890ff" }} />}
              onClick={(e) => {
                e.stopPropagation();
                handleOpenTagEdit(record);
              }}
              style={{
                padding: 0,
                minWidth: "auto",
                height: "auto",
                flexShrink: 0,
              }}
            />
          </div>
        );
      },
    },
    {
      title: "所在目录",
      dataIndex: "rel_path",
      width: 120,
      render: (rel_path: string) => {
        if (rel_path?.length) {
          const relArr = rel_path?.split("/");
          if (relArr?.[1]) {
            return relArr?.[0];
          }
          if (
            ["pdf", "docx", "doc", "pptx"].includes(
              rel_path?.split(".")?.at(-1) ?? "",
            )
          ) {
            return "/";
          }
          if (!relArr?.[1]?.length) {
            return "/";
          }
          return rel_path;
        }
        return "/";
      },
    },
    {
      title: "解析状态",
      dataIndex: "document_stage",
      width: 120,
      render: (document_stage: string) => {
        return DocumentStageEnum[
          document_stage as keyof typeof DocumentStageEnum
        ];
      },
    },
    {
      title: "知识类型",
      dataIndex: "type",
      width: 120,
      render: (type: string, record: DocRow) => {
        if (type === DocTypeEnum.Folder) {
          return "文件夹";
        }
        return FileUtils.getSuffix(record.display_name || "") || "未知";
      },
    },
    {
      title: "大小",
      dataIndex: "document_size",
      width: 120,
      render: (_: number, record: DocRow) => {
        return FileUtils.formatFileSize(record.document_size);
      },
    },
    {
      title: "更新日期",
      dataIndex: "update_time",
      width: 180,
      render: (text: string) => moment(text).format(TIME_FORMAT),
    },
    {
      title: "更新人",
      dataIndex: "creator",
      width: 120,
    },
  ];

  function getTags() {
    KnowledgeBaseServiceApi()
      .datasetServiceAllDatasetTags()
      .then((res) => {
        setTags([ALL_TAGS, ...res.data.tags]);
      })
      .catch(() => {
        setTags([ALL_TAGS]);
      });
  }

  // 统一的成功和错误处理函数
  const handleSuccess = (
    data: Dataset[],
    total: number,
    newPagination: TablePaginationConfig,
  ) => {
    setDataSource(data);
    setPagination({
      ...newPagination,
      total,
    });
  };

  // 初始化数据
  const initData = () => {
    setDataSource([]);
    setPagination({
      current: 1,
      pageSize: 10,
      total: 0,
    });
  };

  function getTableData(page = 1, pageSize = pagination.pageSize) {
    form.validateFields().then((values) => {
      // 更新分页状态
      const newPagination = {
        ...pagination,
        current: page,
        pageSize: pageSize,
      };
      setPagination(newPagination);

      // 生成 pageToken
      const pageToken = UIUtils.generatePageToken({
        page: page - 1,
        pageSize: pageSize || 10,
        total: pagination.total || 0,
      });

      setLoading(true);

      // 根据类型调用不同的 API
      if (knowledgeType === "knowledgeBase") {
        KnowledgeBaseServiceApi()
          .datasetServiceListDatasets({
            pageToken,
            pageSize: pageSize,
            keyword: values.keyword,
            tags: values?.tags === ALL_TAGS ? [] : [values?.tags],
          })
          .then((res) => {
            handleSuccess(
              res.data.datasets || [],
              res.data.total_size || 0,
              newPagination,
            );
          })
          .catch(() => {
            initData();
          })
          .finally(() => {
            setLoading(false);
          });
      } else {
        DocumentServiceApi()
          .documentServiceSearchAllDocuments({
            searchAllDocumentsRequest: {
              page_token: pageToken,
              page_size: pageSize,
              keyword: values.keyword || "",
            },
          })
          .then((res) => {
            handleSuccess(
              (res.data.documents as unknown as Dataset[]) || [],
              res.data.total_size || 0,
              newPagination,
            );
          })
          .catch(() => {
            initData();
          })
          .finally(() => {
            setLoading(false);
          });
      }
    });
  }

  function onDelete(id: string) {
    KnowledgeBaseServiceApi()
      .datasetServiceDeleteDataset({ dataset: id })
      .then(() => {
        message.success("删除知识库成功！");
        getTags();
        getTableData();
      });
  }

  function onUpdate(data: Dataset): Promise<void> {
    setLoading(true);
    try {
      if (data.dataset_id) {
        return KnowledgeBaseServiceApi()
          .datasetServiceUpdateDataset({
            dataset: data.dataset_id,
            dataset2: data,
          })
          .then(() => {
            message.success("编辑知识库成功");
            getTags();
            getTableData();
          });
      }
      return KnowledgeBaseServiceApi()
        .datasetServiceCreateDataset({
          dataset: data,
        })
        .then(() => {
          message.success(`${data.dataset_id ? "编辑" : "创建"}知识库成功`);
          getTags();
          getTableData();
        });
    } finally {
      setLoading(false);
    }
  }
  function onTableChange(newPagination: TablePaginationConfig) {
    setPagination({
      current: newPagination.current,
      pageSize: newPagination.pageSize,
    });

    getTableData(newPagination.current, newPagination.pageSize);
  }

  return (
    <div className="knowledge-list-page">
      <div className="knowledge-title">知识库</div>
      <Form className="list-header" form={form}>
        <ListPageHeader
          placeholder={
            knowledgeType === "knowledgeBase"
              ? "知识库名称/描述/标签"
              : "搜索文档名称、标签、更新人"
          }
          searchKey="keyword"
          btnText={"创建知识库"}
          onClick={() => {
            createUpdateRef.current?.onOpen();
          }}
          onSearch={() => {
            getTableData();
          }}
          extra={
            <>
              {knowledgeType === "knowledgeBase" && (
                <Form.Item
                  label="标签"
                  name="tags"
                  style={{ marginBottom: 0 }}
                  initialValue={ALL_TAGS}
                >
                  <Select
                    className="ghost-custom-border !w-[260px]"
                    options={tags.map((tag) => ({ label: tag, value: tag }))}
                    placeholder="请选择知识库标签"
                    allowClear
                    variant="borderless"
                    onChange={() => {
                      getTableData();
                    }}
                  />
                </Form.Item>
              )}
            </>
          }
          prefix={
            <Select
              className="ghost-custom-border !w-[100px]"
              options={[
                { key: "knowledgeBase", value: "知识库" },
                { key: "knowledge", value: "知识" },
              ].map(({ key, value }) => ({ label: value, value: key }))}
              variant="borderless"
              onChange={(key) => {
                // 切换类型时清空搜索框和标签
                form.resetFields(["keyword", "tags"]);
                initData();
                // 重置标签为默认值
                form.setFieldsValue({ tags: ALL_TAGS });
                setKnowledgeType(key);
              }}
              defaultValue={knowledgeType}
            />
          }
        />
      </Form>
      <ListPageTable
        rowKey={
          knowledgeType === "knowledgeBase" ? "dataset_id" : "document_id"
        }
        columns={knowledgeType === "knowledgeBase" ? columns : knowledgeColumns}
        loading={loading}
        dataSource={dataSource}
        expandable={{ showExpandColumn: false }}
        pagination={{
          ...pagination,
          showSizeChanger: true,
          showTotal: (total: number) => `共 ${total} 条`,
        }}
        onChange={onTableChange}
        scroll={{
          y: "calc(100vh - 260px)",
        }}
      />

      <ConfirmModal ref={confirmRef} onClick={onDelete} />

      <CreateUpdateModal ref={createUpdateRef} onUpdate={onUpdate} />
      <EditTags
        open={showTagEditModal}
        record={tagEditRecord as TreeNode | null}
        datasetId={tagEditRecord?.dataset_id ?? ""}
        onCancel={handleCloseTagEdit}
        onSuccess={handleTagEditSuccess}
      />
    </div>
  );
};

export default KnowledgePage;

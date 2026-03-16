import { forwardRef, useImperativeHandle, useState, useEffect } from "react";
import {
  Alert,
  Button,
  Empty,
  Flex,
  Form,
  message,
  Modal,
  Select,
  Spin,
  Steps,
  Table,
} from "antd";
import {
  DeleteOutlined,
  InboxOutlined,
  LoadingOutlined,
  PaperClipOutlined,
} from "@ant-design/icons";
import "./index.scss";
import Upload, { RcFile } from "antd/es/upload";
import {
  ChatFileServiceApi,
  ChatServiceApi,
  DatabaseBaseServiceApi,
  KnowledgeBaseServiceApi,
} from "@/modules/chat/utils/request";
import { Dataset, UserDatabaseSummary } from "@/api/generated/knowledge-client";
import {
  BatchChatJob,
  BatchChatJobResultItem,
  SearchKnowledgeConfig,
} from "@/api/generated/chatbot-client";
import { downloadUrl } from "@/modules/chat/utils/download";
import RiskTip from "../RiskTip";
const { Dragger } = Upload;

interface ForwardProps {
  cancelFn: (dotBool: string) => void;
}

const initialValues = {
  knowledge: null,
  database: null,
  file: [],
};

export interface BatchChatImperativeProps {
  onOpen: () => void;
}

let timer: number | undefined;
const BatchChatComponent = forwardRef<BatchChatImperativeProps, ForwardProps>(
  (props, ref) => {
    const { cancelFn } = props;
    const batchChatTask = localStorage.getItem("batchChatTask");
    const batchChatJobId = localStorage.getItem("batchChatJobId");
    const [visible, setVisible] = useState(false);
    const items = [{ title: "导入数据" }, { title: "导出结果" }];
    const [current, setCurrent] = useState(0);
    const templateUrl = new URL("/批量对话模板.xlsx", import.meta.url).href;
    const [form] = Form.useForm();
    const [loading, setLoading] = useState(false);
    const [dataSource, setDataSource] = useState<BatchChatJobResultItem[]>([]);
    const [knowledgeBaseList, setKnowledgeBaseList] = useState<Dataset[]>([]);
    const [databaseBaseList, setDatabaseBaseList] = useState<
      UserDatabaseSummary[]
    >([]);
    const [uploadFile, setUploadFile] = useState<RcFile>();
    const [fileId, setFileId] = useState("");
    const [batchChatTaskResult, setBatchChatTaskResult] =
      useState<BatchChatJob>({} as BatchChatJob);

    function getDatabaseBaseList() {
      DatabaseBaseServiceApi()
        .databaseServiceGetUserDatabaseSummaries({})
        .then((res) => {
          setDatabaseBaseList((res.data as UserDatabaseSummary[]) || []);
        });
    }

    function getKnowledgeBaseList() {
      KnowledgeBaseServiceApi()
        .datasetServiceListDatasets({ pageSize: 1000 })
        .then((res) => {
          setKnowledgeBaseList(res.data.datasets || []);
        });
    }

    function getFileReviewResult(job: string) {
      ChatServiceApi()
        .conversationServicePreviewBatchChatJobResult({ job })
        .then((res) => {
          const data =
            res?.data?.items
              ?.slice(0, 10)
              ?.map((it, i) => ({ ...it, index: i + 1 })) || [];
          setDataSource(data);
        });
    }

    function getFileResult(job: string) {
      ChatServiceApi()
        .conversationServiceGetBatchChatJob({ job })
        .then((res) => {
          const { status } = res.data;
          setBatchChatTaskResult(res.data);
          clearInterval(timer);
          if (status !== "BATCH_CHAT_JOB_STATUS_SUCCESS") {
            timer = setInterval(() => {
              getFileResult(job);
            }, 5000);
          } else {
            getFileReviewResult(job);
            setLoading(false);
          }
        });
    }

    function onFinish(values: any) {
      const { knowledge, database } = values;
      if (!uploadFile?.uid?.length) {
        message.error("请上传文件");
        return;
      }
      ChatServiceApi()
        .conversationServiceBatchChat({
          batchChatRequest: {
            conversation: {
              search_config: {
                dataset_list: knowledge ? [{ id: knowledge }] : [],
                database_ids: database ? [database] : [],
              } as SearchKnowledgeConfig,
            },
            file_id: fileId,
          },
        })
        .then((res) => {
          localStorage.setItem("batchChatJobId", res?.data.job_id || "");
          getFileResult(res?.data.job_id || "");
          setLoading(true);
          setCurrent(1);
        });
    }

    useEffect(() => {
      if (batchChatTask === "true") {
        setCurrent(1);
        setLoading(true);
        getFileResult(batchChatJobId || "");
      }
    }, [batchChatTask]);

    useEffect(() => {
      getKnowledgeBaseList();
      getDatabaseBaseList();
    }, []);

    const columns = [
      {
        title: "序号",
        dataIndex: "index",
        width: 100,
      },
      {
        title: "问题",
        dataIndex: "question",
      },
      {
        title: "答案",
        dataIndex: "answer",
      },
    ];

    useImperativeHandle(ref, () => ({
      onOpen: () => {
        setVisible(true);
      },
    }));

    function uploadFileChange(file: RcFile) {
      setUploadFile(file);
      ChatFileServiceApi()
        .fileServicePresignAttachment({
          presignAttachmentRequest: {
            file: file.name,
            file_size: file.size + "",
          },
        })
        .then((res) => {
          const { file_id, uri } = res.data;
          setFileId(file_id || "");
          fetch(uri!, {
            method: "PUT",
            body: file,
          }).then((data) => {
            console.log(data, "上传成功");
          });
        });
    }

    return (
      <Modal
        title="批量对话"
        width={1000}
        open={visible}
        maskClosable={false}
        closable={false}
        footer={null}
      >
        <Steps current={current} items={items} className="!p-6" />
        <div className="batch-chat-content px-10">
          {current === 0 && (
            <div className="batch-chat-content-item mt-8">
              <Form
                form={form}
                labelCol={{ span: 2 }}
                onFinish={onFinish}
                initialValues={initialValues}
              >
                <Form.Item label="知识库" name="knowledge">
                  <Select
                    options={knowledgeBaseList.map((knowledgeBase) => ({
                      value: knowledgeBase.dataset_id,
                      label: knowledgeBase.display_name,
                    }))}
                    placeholder="请选择知识库"
                  />
                </Form.Item>
                {/* <Form.Item label="数据库" name="database">
                <Select
                  options={databaseBaseList.map((db) => ({
                    value: db.id,
                    label: db.name,
                  }))}
                  placeholder="请选择数据库"
                />
              </Form.Item> */}
                <Form.Item label="文件" name="file">
                  <Dragger
                    showUploadList={false}
                    maxCount={1}
                    accept={".xlsx"}
                    beforeUpload={() => false}
                    onChange={(info) => {
                      if (!uploadFile?.uid?.length) {
                        uploadFileChange(info.file as RcFile);
                      } else {
                        message.warning("最多上传1个文件");
                      }
                    }}
                    className="drag-upload-container"
                  >
                    <p className="ant-upload-drag-icon">
                      <InboxOutlined />
                    </p>
                    <p className="ant-upload-text">
                      <span style={{ marginRight: 4 }}>点击或者拖拽上传</span>
                      <RiskTip />
                    </p>
                    <p className="ant-upload-hint">
                      上传文件格式： .xlsx ，大小不超过 {5} MB。
                      <br />
                      excel 文件仅识别第一个表单，如有多个表单，请分次导入
                    </p>
                  </Dragger>
                </Form.Item>
                <Form.Item>
                  {uploadFile?.uid?.length && (
                    <Flex>
                      <PaperClipOutlined />
                      <div style={{ margin: "0 20px" }}>{uploadFile?.name}</div>
                      <DeleteOutlined
                        onClick={() => {
                          if (uploadFile?.uid.length) {
                            setUploadFile(undefined);
                          }
                        }}
                      />
                    </Flex>
                  )}
                </Form.Item>
                <Form.Item>
                  <div className="mt-8 flex items-center justify-between">
                    <div>
                      <Alert
                        message={
                          <span>
                            可查看
                            <a
                              href={templateUrl}
                              target="_self"
                              download="批量对话模板.xlsx"
                            >
                              模板
                            </a>
                          </span>
                        }
                        type="warning"
                        showIcon
                      />
                    </div>
                    <div>
                      <Button onClick={() => setVisible(false)}>取消</Button>
                      <Button type="primary" htmlType="submit" className="ml-4">
                        确定
                      </Button>
                    </div>
                  </div>
                </Form.Item>
              </Form>
            </div>
          )}
          {current === 1 && (
            <div className="batch-chat-content-item">
              {loading ? (
                <div>
                  <Empty
                    description={
                      <div className="flex items-center justify-center gap-4">
                        <Spin indicator={<LoadingOutlined spin />} />
                        <p>{`返回结果中: ${batchChatTaskResult.success_num ?? 0}/${batchChatTaskResult.total_num ?? 0},请耐心等待`}</p>
                      </div>
                    }
                  />
                </div>
              ) : (
                <Table
                  columns={columns}
                  dataSource={dataSource}
                  pagination={false}
                />
              )}
              <div className="mt-8 flex items-center justify-between">
                <div>
                  {loading && (
                    <Alert
                      message={`共${batchChatTaskResult.total_num}条记录，当前预览只展示前 ${batchChatTaskResult.total_num! >= 10 ? 10 : batchChatTaskResult.total_num} 条记录`}
                      type="warning"
                      showIcon
                    />
                  )}
                </div>
                <div>
                  {!loading && (
                    <Button
                      onClick={() => {
                        clearInterval(timer);
                        cancelFn("false");
                        localStorage.setItem("batchChatTask", "false");
                        localStorage.setItem("batchChatJobId", "");
                        setCurrent(0);
                        form.resetFields();
                        setUploadFile(undefined);
                        setVisible(false);
                      }}
                    >
                      关闭
                    </Button>
                  )}
                  <Button
                    className="ml-4"
                    onClick={() => {
                      clearInterval(timer);
                      cancelFn("false");
                      localStorage.setItem("batchChatTask", "false");
                      localStorage.setItem("batchChatJobId", "");
                      setCurrent(0);
                      form.resetFields();
                      setUploadFile(undefined);
                      // 取消
                      if (loading) {
                        setVisible(false);
                      }
                    }}
                  >
                    {loading ? "取消" : "重新导入"}
                  </Button>
                  <Button
                    type="primary"
                    onClick={() => {
                      if (loading) {
                        // 最小化
                        localStorage.setItem("batchChatTask", "true");
                        cancelFn("true");
                      } else {
                        // 导出结果
                        if (batchChatTaskResult?.result_file_uri) {
                          downloadUrl(batchChatTaskResult?.result_file_uri);
                        }
                        cancelFn("false");
                        localStorage.setItem("batchChatTask", "false");
                      }
                      setVisible(false);
                    }}
                    className="ml-4"
                  >
                    {loading ? "最小化" : "导出结果"}
                  </Button>
                </div>
              </div>
            </div>
          )}
        </div>
      </Modal>
    );
  },
);

BatchChatComponent.displayName = "BatchChatComponent";

export default BatchChatComponent;

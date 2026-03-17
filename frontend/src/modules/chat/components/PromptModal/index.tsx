import { forwardRef, useImperativeHandle, useState } from "react";
import { Modal, Button, Input, Divider, Form, message, Tag, Tabs } from "antd";
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  PushpinFilled,
  PushpinOutlined,
} from "@ant-design/icons";
import { useEffect } from "react";

import { PromptServiceApi } from "@/modules/chat/utils/request";
import "./index.scss";
import {
  Prompt,
  PromptServiceApiPromptServiceUpdatePromptRequest,
  PromptServiceApiPromptServiceCreatePromptRequest,
} from "@/api/generated/chatbot-client";

interface ForwardProps {
  onSelectPrompt: (prompt: string) => void;
}

type updateParams =
  | PromptServiceApiPromptServiceUpdatePromptRequest
  | PromptServiceApiPromptServiceCreatePromptRequest;

export interface PromptImperativeProps {
  onOpen: () => void;
}

const { TextArea } = Input;

// 预置的提示词模板（置顶且不可编辑）
const PRESET_PROMPTS: Array<
  Pick<Prompt, "id" | "display_name" | "content"> & { isPreset: boolean }
> = [
  {
    id: "preset-1",
    display_name: "通用问答助手",
    content:
      "请根据我提供的文档内容，简洁明了地回答我的问题。如果文档中没有相关信息，请直接告知。",
    isPreset: true,
  },
  {
    id: "preset-2",
    display_name: "文档摘要提取",
    content:
      "请帮我总结一下这份文档的核心内容，并列出其中的关键要点。",
    isPreset: true,
  },
  {
    id: "preset-3",
    display_name: "结构化信息提取",
    content:
      "请从文档中提取出所有的日期、参与方和主要结论，并以表格的形式呈现。",
    isPreset: true,
  },
];

const PromptModal = forwardRef<PromptImperativeProps, ForwardProps>(
  ({ onSelectPrompt }, ref) => {
    const [visible, setVisible] = useState(false);
    const [addModalVisible, setAddModalVisible] = useState(false);
    const [isEdit, setIsEdit] = useState(false);
    const [editPromptId, setEditPromptId] = useState<string | undefined>("");

    const [form] = Form.useForm();

    const [promptList, setPromptList] = useState<Prompt[]>([]);

    useEffect(() => {
      fetchPromptList();
    }, []);

    useImperativeHandle(ref, () => ({
      onOpen,
    }));

    function fetchPromptList() {
      PromptServiceApi()
        .promptServiceListPrompts({ pageSize: 2 })
        .then((res) => {
          setPromptList(res.data.prompts ? [...res.data?.prompts] : []);
        });
    }

    function onOpen() {
      setVisible(true);
      // 每次打开弹窗时重新拉取列表，保证图一/图二等多处入口看到的数据一致
      fetchPromptList();
    }

    function showAddPromptModal(prompt?: Prompt) {
      form.setFieldsValue({
        display_name: prompt ? prompt.display_name : "",
        content: prompt ? prompt.content : "",
      });
      setIsEdit(!!prompt);
      setEditPromptId(prompt?.id);
      setAddModalVisible(true);
    }

    function deletePrompt(id: string) {
      PromptServiceApi()
        .promptServiceDeletePrompt({ prompt: id })
        .then(() => {
          message.success("删除提示词成功");
          fetchPromptList();
        });
    }

    function selectPrompt(content: string) {
      setVisible(false);
      onSelectPrompt(content);
    }

    function onAddModalClose() {
      setAddModalVisible(false);
    }

    function onAddModalSave() {
      form.validateFields().then((values: Prompt) => {
        const data: updateParams = isEdit
          ? {
              prompt: editPromptId || "",
              prompt2: values,
            }
          : {
              prompt: values,
            };
        const API = isEdit
          ? PromptServiceApi().promptServiceUpdatePrompt
          : PromptServiceApi().promptServiceCreatePrompt;
        API(data as any).then(() => {
          message.success(`${isEdit ? "编辑" : "新建"}提示词成功`);
          onAddModalClose();
          fetchPromptList();
        });
      });
    }

    function setDefaultPromptFn(item: Prompt) {
      if (item.is_default) {
        PromptServiceApi()
          .promptServiceUnsetDefaultPrompt({
            prompt: item?.id ?? "",
            unsetDefaultPromptRequest: {
              name: "",
            },
          })
          .then(() => {
            fetchPromptList();
          });
        return;
      }
      PromptServiceApi()
        .promptServiceSetDefaultPrompt({
          prompt: item?.id ?? "",
          setDefaultPromptRequest: {
            name: "",
          },
        })
        .then(() => {
          fetchPromptList();
        });
    }

    function renderDefaultItem(
      item: Prompt,
      isSelected: boolean,
      isDefault: boolean,
    ) {
      if (isSelected) {
        if (isDefault) {
          return (
            <PushpinFilled
              style={{ color: "#1890ff" }}
              onClick={(e) => {
                e.stopPropagation();
                setDefaultPromptFn(item);
              }}
            />
          );
        }
        return (
          <PushpinOutlined
            className="cancelDefaultDataset prompt-actions"
            onClick={(e) => {
              e.stopPropagation();
              setDefaultPromptFn(item);
            }}
          />
        );
      }
      return null;
    }

    // 自定义模版 Tab 内容
    const renderCustomTab = () => (
      <div className="prompt-tab-content">
        <div className="prompt-add-card" onClick={() => showAddPromptModal()}>
          <PlusOutlined className="prompt-add-icon" />
          <span className="prompt-add-text">新建模版</span>
        </div>
        <div className="prompt-list">
          {promptList.map((prompt, index) => (
            <div key={prompt.id} className="prompt-item">
              <div className="prompt-title">
                <div className="prompt-name">
                  <span className="prompt-index">{index + 1}</span>
                  <span className="prompt-name-text">
                    {prompt.display_name}
                  </span>
                  {renderDefaultItem(prompt, true, prompt.is_default ?? false)}
                </div>
                <div className="prompt-actions">
                  <EditOutlined
                    className="clickable-icon"
                    onClick={() => showAddPromptModal(prompt)}
                  />
                  <DeleteOutlined
                    className="clickable-icon"
                    onClick={() => deletePrompt(prompt.id)}
                  />
                  <Button
                    type="link"
                    onClick={() => selectPrompt(prompt.content)}
                    style={{ padding: 0 }}
                  >
                    使用
                  </Button>
                </div>
              </div>
              <div style={{ height: "10px" }}></div>
              <span className="prompt-content">{prompt.content}</span>
              <Divider style={{ margin: "10px 0" }} />
            </div>
          ))}
        </div>
      </div>
    );

    // 预置模版 Tab 内容
    const renderPresetTab = () => (
      <div className="prompt-tab-content">
        <div className="prompt-list">
          {PRESET_PROMPTS.map((prompt) => (
            <div key={prompt.id} className="prompt-item">
              <div className="prompt-title">
                <div className="prompt-name">
                  <Tag color="geekblue">预置</Tag>
                  <span className="prompt-name-text">
                    {prompt.display_name}
                  </span>
                </div>
                <div className="prompt-actions">
                  <Button
                    type="link"
                    onClick={() => selectPrompt(prompt.content)}
                    style={{ padding: 0 }}
                  >
                    使用
                  </Button>
                </div>
              </div>
              <Divider style={{ margin: "3px 0" }} />
              <span className="prompt-content">{prompt.content}</span>
            </div>
          ))}
        </div>
      </div>
    );

    const tabItems = [
      {
        key: "custom",
        label: "自定义模版",
        children: renderCustomTab(),
      },
      {
        key: "preset",
        label: "预置模版",
        children: renderPresetTab(),
      },
    ];

    return (
      <>
        <Modal
          title="提示词模版"
          className="prompt-modal"
          width={624}
          open={visible}
          maskClosable
          closable
          onCancel={() => setVisible(false)}
          footer={[
            <Button key="cancel" onClick={() => setVisible(false)}>
              取消
            </Button>,
          ]}
        >
          <div className="prompt-modal-container">
            <Tabs
              defaultActiveKey="custom"
              items={tabItems}
              className="prompt-modal-tabs"
            />
          </div>
        </Modal>
        <Modal
          title={`${isEdit ? "编辑" : "新增"} 提示词模板`}
          open={addModalVisible}
          maskClosable={false}
          closable
          okText="保存"
          onCancel={onAddModalClose}
          onOk={onAddModalSave}
        >
          <Form form={form}>
            <Form.Item
              name="display_name"
              label={"标题"}
              rules={[{ required: true, message: "请输入提示词标题" }]}
            >
              <Input
                placeholder={"请输入提示词标题"}
                showCount
                maxLength={100}
              />
            </Form.Item>
            <Form.Item
              name="content"
              label={"内容"}
              rules={[{ required: true, message: "请输入提示词内容" }]}
            >
              <TextArea
                placeholder={"请输入提示词内容"}
                rows={5}
                showCount
                maxLength={800}
              />
            </Form.Item>
          </Form>
        </Modal>
      </>
    );
  },
);

PromptModal.displayName = "PromptModal";

export default PromptModal;

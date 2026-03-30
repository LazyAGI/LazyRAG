import { forwardRef, useImperativeHandle, useState, useEffect, useMemo } from "react";
import { Modal, Button, Input, Divider, Form, message, Tag, Tabs } from "antd";
import { useTranslation } from "react-i18next";
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  PushpinFilled,
  PushpinOutlined,
} from "@ant-design/icons";
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

const PRESET_PROMPT_IDS = ["preset-1", "preset-2", "preset-3"] as const;

const PromptModal = forwardRef<PromptImperativeProps, ForwardProps>(
  ({ onSelectPrompt }, ref) => {
    const { t } = useTranslation();

    const presetPrompts = useMemo(
      () =>
        PRESET_PROMPT_IDS.map((id, index) => ({
          id,
          display_name: t(`chat.presetPrompt${index + 1}Name`),
          content: t(`chat.presetPrompt${index + 1}Content`),
          isPreset: true as const,
        })),
      [t],
    );
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
          message.success(t("chat.deletePromptSuccess"));
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
          message.success(
            t("chat.createPromptSuccess", {
              action: isEdit ? t("common.edit") : t("chat.newTemplate"),
            }),
          );
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

    const renderCustomTab = () => (
      <div className="prompt-tab-content">
        <div className="prompt-add-card" onClick={() => showAddPromptModal()}>
          <PlusOutlined className="prompt-add-icon" />
          <span className="prompt-add-text">{t("chat.newTemplate")}</span>
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
                    {t("chat.use")}
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

    const renderPresetTab = () => (
      <div className="prompt-tab-content">
        <div className="prompt-list">
          {presetPrompts.map((prompt) => (
            <div key={prompt.id} className="prompt-item">
              <div className="prompt-title">
                <div className="prompt-name">
                  <Tag color="geekblue">{t("chat.preset")}</Tag>
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
                    {t("chat.use")}
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
        label: t("chat.customTemplate"),
        children: renderCustomTab(),
      },
      {
        key: "preset",
        label: t("chat.presetTemplate"),
        children: renderPresetTab(),
      },
    ];

    return (
      <>
        <Modal
          title={t("chat.promptTemplateTitle")}
          className="prompt-modal"
          width={624}
          open={visible}
          maskClosable
          closable
          onCancel={() => setVisible(false)}
          footer={[
            <Button key="cancel" onClick={() => setVisible(false)}>
              {t("common.cancel")}
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
          title={isEdit ? t("chat.editPromptTemplate") : t("chat.addPromptTemplate")}
          open={addModalVisible}
          maskClosable={false}
          closable
          okText={t("common.save")}
          onCancel={onAddModalClose}
          onOk={onAddModalSave}
        >
          <Form form={form}>
            <Form.Item
              name="display_name"
              label={t("chat.promptTitle")}
              rules={[{ required: true, message: t("chat.enterPromptTitle") }]}
            >
              <Input
                placeholder={t("chat.enterPromptTitle")}
                showCount
                maxLength={100}
              />
            </Form.Item>
            <Form.Item
              name="content"
              label={t("chat.promptContent")}
              rules={[{ required: true, message: t("chat.enterPromptContent") }]}
            >
              <TextArea
                placeholder={t("chat.enterPromptContent")}
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

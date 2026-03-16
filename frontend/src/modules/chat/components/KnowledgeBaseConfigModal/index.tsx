/* eslint-disable react/display-name */
import { forwardRef, useEffect, useImperativeHandle, useState } from "react";
import { Modal, Form, Select } from "antd";
import { UserInfo } from "@/api/generated/knowledge-client";

import { DocumentServiceApi } from "@/modules/chat/utils/request";
import { ChatConfig } from "../ChatConfigs";

interface ForwardProps {
  onChange: (configs: ChatConfig) => void;
}

export interface ConfigImperativeProps {
  onOpen: (configs: ChatConfig) => void;
}

const KnowledgeBaseConfigModal = forwardRef<
  ConfigImperativeProps,
  ForwardProps
>(({ onChange }, ref) => {
  const [visible, setVisible] = useState(false);
  const [creators, setCreators] = useState<UserInfo[]>([]);
  const [tags, setTags] = useState<string[]>([]);

  const [form] = Form.useForm();

  useImperativeHandle(ref, () => ({
    onOpen,
  }));

  useEffect(() => {
    fetchCreators();
    fetchTags();
  }, []);

  function fetchCreators() {
    DocumentServiceApi()
      .documentServiceAllDocumentCreators()
      .then((res) => {
        setCreators(res.data.creators || []);
      });
  }

  function fetchTags() {
    DocumentServiceApi()
      .documentServiceAllDocumentTags()
      .then((res) => {
        setTags(res.data.tags || []);
      });
  }

  const onOpen = (chatConfigs: ChatConfig) => {
    form.setFieldsValue(chatConfigs);
    setVisible(true);
  };

  const onCancel = () => {
    setVisible(false);
    form.resetFields();
  };

  return (
    <Modal
      title={"知识库高级配置"}
      open={visible}
      maskClosable={false}
      onCancel={onCancel}
      onOk={() => {
        onChange(form.getFieldsValue());
        onCancel();
      }}
    >
      <Form form={form} layout="vertical">
        <Form.Item label={"文档创建人"} name="creators">
          <Select
            mode="multiple"
            tokenSeparators={[" "]}
            allowClear
            placeholder={"请选择文档创建人"}
            popupMatchSelectWidth
            showSearch
            style={{ flex: 1 }}
            filterOption={false}
            options={creators.map((creator) => {
              return { value: creator.id, label: creator.name };
            })}
          />
        </Form.Item>
        <Form.Item label={"文档标签"} name="tags">
          <Select
            mode="multiple"
            tokenSeparators={[" "]}
            allowClear
            placeholder={"请选择文档标签"}
            popupMatchSelectWidth
            showSearch
            optionLabelProp="value"
            style={{ flex: 1 }}
            filterOption={false}
            options={tags.map((tag) => {
              return { value: tag, label: tag };
            })}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
});

export default KnowledgeBaseConfigModal;

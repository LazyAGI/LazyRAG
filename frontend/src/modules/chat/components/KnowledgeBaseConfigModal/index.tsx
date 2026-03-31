/* eslint-disable react/display-name */
import { forwardRef, useEffect, useImperativeHandle, useState } from "react";
import { Modal, Form, Select } from "antd";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation();
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
      title={t("chat.knowledgeAdvancedConfig")}
      open={visible}
      maskClosable={false}
      onCancel={onCancel}
      onOk={() => {
        onChange(form.getFieldsValue());
        onCancel();
      }}
    >
      <Form form={form} layout="vertical">
        <Form.Item label={t("chat.documentCreator")} name="creators">
          <Select
            mode="multiple"
            tokenSeparators={[" "]}
            allowClear
            placeholder={t("chat.selectCreator")}
            popupMatchSelectWidth
            showSearch
            style={{ flex: 1 }}
            filterOption={false}
            options={creators.map((creator) => {
              return { value: creator.id, label: creator.name };
            })}
          />
        </Form.Item>
        <Form.Item label={t("chat.documentTag")} name="tags">
          <Select
            mode="multiple"
            tokenSeparators={[" "]}
            allowClear
            placeholder={t("chat.selectTag")}
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

import { useEffect, useMemo, useState } from "react";
import { Form, message, Modal, Radio, Select, Space, Tooltip } from "antd";
import { useTranslation } from "react-i18next";
import { InfoCircleOutlined } from "@ant-design/icons";
import { DocumentServiceApi } from "@/modules/knowledge/utils/request";
import { BatchUpdateDocumentTagsRequestModeEnum } from "@/api/generated/knowledge-client";

type EditMode = "append" | "overwrite";

interface BatchEditTagsProps {
  open: boolean;
  selectedFileCount: number;
  documentIds: string[];
  folderIds: string[];
  datasetId: string;
  onCancel: () => void;
  onSuccess: () => void;
}

const MAX_TAG_LENGTH = 25;

const normalizeTags = (tags: string[]) => {
  const cleaned = (tags || []).map((t) => (t ?? "").trim()).filter(Boolean);
  return Array.from(new Set(cleaned));
};

const BatchEditTags = ({
  open,
  selectedFileCount,
  documentIds,
  folderIds,
  datasetId,
  onCancel,
  onSuccess,
}: BatchEditTagsProps) => {
  const { t } = useTranslation();
  const [form] = Form.useForm<{ mode: EditMode; tags: string[] }>();
  const [tagOptions, setTagOptions] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  const parent = useMemo(() => `datasets/${datasetId}`, [datasetId]);

  useEffect(() => {
    if (!open) {
      return;
    }
    form.resetFields();
    DocumentServiceApi()
      .documentServiceAllDocumentTags()
      .then((res) => setTagOptions(res.data.tags || []))
      .catch((error) => {
        console.error("Failed to load tags:", error);
      });
  }, [open, form]);

  const selectOptions = useMemo(
    () =>
      tagOptions.map((option) => ({
        value: option,
        label: option,
      })),
    [tagOptions],
  );

  const buildRequest = (mode: EditMode, tags: string[]) => ({
    dataset: datasetId,
    batchUpdateDocumentTagsRequest: {
      parent,
      mode:
        mode === "append"
          ? BatchUpdateDocumentTagsRequestModeEnum.Append
          : BatchUpdateDocumentTagsRequestModeEnum.Overwrite,
      tags,
      ...(documentIds.length ? { document_ids: documentIds } : {}),
      ...(folderIds.length ? { folder_ids: folderIds } : {}),
    },
  });

  const handleOk = async () => {
    if (!selectedFileCount) {
      message.warning(t("knowledge.selectAtLeastOneFile"));
      return;
    }
    try {
      const { mode, tags } = await form.validateFields();
      const pickedTags = normalizeTags(tags || []);
      if (pickedTags.length > 10) {
        message.warning(t("knowledge.maxTenTags"));
        return;
      }

      const invalidTags = pickedTags.filter(
        (tag) => tag.length > MAX_TAG_LENGTH,
      );
      if (invalidTags.length > 0) {
        message.error(t("knowledge.singleTagMaxLength", { count: MAX_TAG_LENGTH }));
        return;
      }

      setLoading(true);

      const res =
        await DocumentServiceApi().documentServiceBatchUpdateDocumentTags(
          buildRequest(mode, pickedTags),
        );

      const affected = res.data.affected_files ?? 0;
      const truncated = res.data.truncated_docs ?? 0;
      if (mode === "append" && truncated > 0) {
        message.success(
          t("knowledge.batchTagsUpdatedTruncated", { affected, truncated }),
        );
      } else {
        message.success(t("knowledge.batchTagsUpdated", { affected }));
      }

      onSuccess();
      onCancel();
    } catch (error) {
      if (error && typeof error === "object" && "errorFields" in error) {
        return;
      }
      console.error("Failed to batch update tags:", error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      open={open}
      title={t("knowledge.batchSetTags")}
      centered
      onCancel={onCancel}
      onOk={handleOk}
      width={720}
      maskClosable={false}
      okButtonProps={{ loading }}
      cancelButtonProps={{ disabled: loading }}
    >
      <Form
        form={form}
        layout="horizontal"
        labelCol={{ flex: "90px" }}
        wrapperCol={{ flex: "auto" }}
        initialValues={{ mode: "append", tags: [] }}
      >
        <div
          style={{
            margin: "-8px 0 12px",
            color: "var(--color-text-description)",
          }}
        >
          {t("knowledge.selectedDocCount", { count: selectedFileCount })}
        </div>

        <Form.Item
          label={t("knowledge.editMode")}
          name="mode"
          rules={[{ required: true, message: t("knowledge.selectEditMode") }]}
        >
          <Radio.Group>
            <Space size={48}>
              <Radio value="append">
                {t("knowledge.appendTags")}
                <Tooltip title={t("knowledge.appendTagsTip")}>
                  <InfoCircleOutlined
                    style={{
                      marginLeft: 6,
                      color: "var(--color-text-description)",
                    }}
                  />
                </Tooltip>
              </Radio>
              <Radio value="overwrite">
                {t("knowledge.overwriteTags")}
                <Tooltip title={t("knowledge.overwriteTagsTip")}>
                  <InfoCircleOutlined
                    style={{
                      marginLeft: 6,
                      color: "var(--color-text-description)",
                    }}
                  />
                </Tooltip>
              </Radio>
            </Space>
          </Radio.Group>
        </Form.Item>

        <Form.Item
          label={t("knowledge.selectTags")}
          name="tags"
          rules={[{ required: true, message: t("knowledge.selectTagRequired") }]}
          normalize={(value?: string[]) => {
            const normalized = normalizeTags(value || []);
            const filtered = normalized.filter(
              (tag) => tag.length <= MAX_TAG_LENGTH,
            );
            return filtered.slice(0, 10);
          }}
        >
          <Select
            mode="tags"
            tokenSeparators={[","]}
            placeholder={t("knowledge.inputOrSelect")}
            options={selectOptions}
            maxCount={10}
            onChange={(value) => {
              if ((value || []).length > 10) {
                message.warning(t("knowledge.maxTenTags"), 3);
                return;
              }
              const invalidTags = (value || []).filter(
                (tag: string) => tag && tag.length > MAX_TAG_LENGTH,
              );
              if (invalidTags.length > 0) {
                message.warning(
                  t("knowledge.singleTagMaxLength", { count: MAX_TAG_LENGTH }),
                  3,
                );
                const validTags = (value || []).filter(
                  (tag: string) => !tag || tag.length <= MAX_TAG_LENGTH,
                );
                form.setFieldValue("tags", validTags);
              }
            }}
            allowClear
          />
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default BatchEditTags;

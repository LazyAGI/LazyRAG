import { useEffect, useMemo, useState } from "react";
import { Form, message, Modal, Radio, Select, Space, Tooltip } from "antd";
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
      message.warning("请至少选择一个文件");
      return;
    }
    try {
      const { mode, tags } = await form.validateFields();
      const pickedTags = normalizeTags(tags || []);
      if (pickedTags.length > 10) {
        message.warning("最多允许选择10个标签");
        return;
      }

      // 验证单个标签长度
      const invalidTags = pickedTags.filter(
        (tag) => tag.length > MAX_TAG_LENGTH,
      );
      if (invalidTags.length > 0) {
        message.error(`单个标签不能超过${MAX_TAG_LENGTH}个字符`);
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
          `已更新${affected}个文件的标签，其中${truncated}个文件的原标签被裁减`,
        );
      } else {
        message.success(`已更新${affected}个文件的标签`);
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
      title="批量设置标签"
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
          已选择 <span style={{ fontWeight: 600 }}>{selectedFileCount}</span>{" "}
          个文档（不含文件夹）
        </div>

        <Form.Item
          label="修改方式"
          name="mode"
          rules={[{ required: true, message: "请选择修改方式" }]}
        >
          <Radio.Group>
            <Space size={48}>
              <Radio value="append">
                追加标签
                <Tooltip title="在原有标签的基础上，追加本次选择标签，请确保各文档的追加后标签不超过10个。">
                  <InfoCircleOutlined
                    style={{
                      marginLeft: 6,
                      color: "var(--color-text-description)",
                    }}
                  />
                </Tooltip>
              </Radio>
              <Radio value="overwrite">
                覆盖标签
                <Tooltip title="覆盖原有标签，标签总数不超过10个">
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
          label="选择标签"
          name="tags"
          rules={[{ required: true, message: "请选择标签" }]}
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
            placeholder="输入或选择..."
            options={selectOptions}
            maxCount={10}
            onChange={(value) => {
              if ((value || []).length > 10) {
                message.warning("最多允许选择10个标签", 3);
                return;
              }
              // 检查单个标签长度
              const invalidTags = (value || []).filter(
                (tag: string) => tag && tag.length > MAX_TAG_LENGTH,
              );
              if (invalidTags.length > 0) {
                message.warning(`单个标签不能超过${MAX_TAG_LENGTH}个字符`, 3);
                // 移除超过长度的标签
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

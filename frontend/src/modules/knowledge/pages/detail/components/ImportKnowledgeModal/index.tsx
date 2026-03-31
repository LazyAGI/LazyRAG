import { Button, Form, message, Modal } from "antd";
import { useTranslation } from "react-i18next";
import {
  forwardRef,
  Ref,
  useEffect,
  useImperativeHandle,
  useState,
} from "react";

import { DataSourceType } from "@/modules/knowledge/constants/common";
import DragUpload from "../DragUpload";
import {
  DocumentServiceApi,
  TaskServiceApi,
  uploadLargeFileToDataset,
} from "@/modules/knowledge/utils/request";
import TagSelect from "@/modules/knowledge/components/TagSelect";
import { useDatasetPermissionStore } from "@/modules/knowledge/store/dataset_permission";

const ALLOWED_FILE_TYPES = ["pdf", "docx", "doc"];
const SINGLE_FILE_MAX_SIZE = 500 * 1024 * 1024;
const TOTAL_FILE_MAX_SIZE = 1 * 1024 * 1024 * 1024;
const ZIP_FILE_TYPES = ["zip"];

const LARGE_FILE_THRESHOLD = 10 * 1024 * 1024; // 10MB

type ImportMode = "file" | "folder" | "zip";

interface IData {
  dataset_id: string;
  targetPath?: string;
  p_id?: string;
  data_source_type?: DataSourceType;
  selectDirectory?: boolean;
  importMode?: ImportMode;
}

export interface IImportKnowledgeModalRef {
  handleOpen: (data: IData) => void;
}

interface IProps {
  onOk: () => void;
}

const InitData = {
  dataset_id: "",
  targetPath: "",
  p_id: "",
  data_source_type: DataSourceType.LOCAL,
  selectDirectory: false,
  importMode: "file" as ImportMode,
};

const ImportKnowledgeModal = (props: IProps, ref: Ref<unknown> | undefined) => {
  const { t } = useTranslation();
  const [data, setData] = useState<IData>(InitData);
  const [visible, setVisible] = useState(false);
  const [loading, setLoading] = useState(false);
  const [tags, setTags] = useState<string[]>([]);
  const [hasZipError, setHasZipError] = useState(false);
  const hasOnlyReadPermission = useDatasetPermissionStore((state) =>
    state.hasOnlyReadPermission(),
  );
  const hasUploadPermission = useDatasetPermissionStore((state) =>
    state.hasUploadPermission(),
  );
  const hasWritePermission = useDatasetPermissionStore((state) =>
    state.hasWritePermission(),
  );
  const isOnlyRead =
    (hasOnlyReadPermission || hasUploadPermission) && !hasWritePermission;

  const { onOk } = props;

  const [form] = Form.useForm();

  useImperativeHandle(ref, () => ({
    handleOpen,
  }));

  useEffect(() => {
    getTags();
  }, []);

  function getTags() {
    DocumentServiceApi()
      .documentServiceAllDocumentTags()
      .then((res) => {
        setTags(res.data.tags);
      });
  }

  function handleOpen(currentData: IData) {
    if (currentData.data_source_type) {
      form.setFieldsValue({ dataSourceType: currentData.data_source_type });
    }
    setData(currentData);
    setVisible(true);
  }

  const importMode: ImportMode =
    data.importMode || (data.selectDirectory ? "folder" : "file");
  const isDirectoryMode = importMode === "folder";
  const isZipMode = importMode === "zip";

  function handleClose() {
    form.resetFields();
    setData(InitData);
    setVisible(false);
    setLoading(false);
  }

  async function submit(values: any) {
    setLoading(true);
    const fileList: File[] = (values.fileList || []).map((f: any) => f.originFile ?? f);

    const smallFiles = fileList.filter((f) => f.size <= LARGE_FILE_THRESHOLD);
    const largeFiles = fileList.filter((f) => f.size > LARGE_FILE_THRESHOLD);

    try {
      const allUploadFileIds: string[] = [];

      if (smallFiles.length > 0) {
        const formData = new FormData();
        smallFiles.forEach((file) => {
          formData.append("files", file);
        });
        if (data.p_id) {
          formData.append("document_pid", data.p_id);
        }
        if (values.tags?.length) {
          formData.append("document_tags", JSON.stringify(values.tags));
        }

        const uploadRes = await TaskServiceApi().uploadFiles(data.dataset_id, formData);
        const uploadedFiles = uploadRes.data.files || [];
        if (!uploadedFiles.length) {
          message.error(t("knowledge.uploadResultMissing"));
          return;
        }
        uploadedFiles.forEach((f) => allUploadFileIds.push(f.upload_file_id));
      }

      for (const file of largeFiles) {
        const uploadFileId = await uploadLargeFileToDataset(data.dataset_id, file, {
          documentPid: data.p_id,
        });
        allUploadFileIds.push(uploadFileId);
      }

      if (!allUploadFileIds.length) {
        message.error(t("knowledge.uploadResultMissing"));
        return;
      }

      const items = allUploadFileIds.map((upload_file_id) => {
        const item: { upload_file_id: string; task?: { document_tags?: string[] } } = {
          upload_file_id,
        };
        if (values.tags?.length) {
          item.task = { document_tags: values.tags };
        }
        return item;
      });

      const createRes = await TaskServiceApi().createTasks(data.dataset_id, { items });
      const taskIds = (createRes.data.tasks || [])
        .map((t) => t.task_id)
        .filter(Boolean) as string[];

      if (!taskIds.length) {
        message.error(t("knowledge.createTaskFailed"));
        return;
      }

      const startMode = hasWritePermission
        ? "DEFAULT"
        : hasUploadPermission
          ? "UPLOAD"
          : undefined;
      await TaskServiceApi().startTasks(data.dataset_id, {
        task_ids: taskIds,
        ...(startMode ? { start_mode: startMode } : {}),
      });

      message.success(t("knowledge.uploadAndCreateTaskSuccess"));
      handleClose();
      onOk();
    } catch (err) {
      console.error(err);
      message.error(t("knowledge.uploadFailedRetry"));
    } finally {
      setLoading(false);
    }
  }

  // function changeSourceType() {
  //   form.resetFields(['fileList', 'urlList', 'notionAccount', 'notionPages'])
  // }

  return (
    <Modal
      open={visible}
      destroyOnHidden
      title={t("knowledge.importFileTitle")}
      onCancel={handleClose}
      centered
      width={896}
      style={{ paddingBottom: 0, minHeight: 300 }}
      className="modal-max-height"
      maskClosable={false}
      footer={
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <Button onClick={handleClose}>{t("common.cancel")}</Button>
          <Button
            type="primary"
            disabled={loading || hasZipError}
            onClick={() => form.submit()}
            style={{ marginLeft: 16 }}
          >
            {isOnlyRead
              ? t("knowledge.uploadKnowledgeFile")
              : t("knowledge.parseAndImport")}
          </Button>
        </div>
      }
    >
      <Form
        form={form}
        layout="vertical"
        colon={false}
        onFinish={submit}
        scrollToFirstError
        initialValues={{
          dataSourceType: DataSourceType.LOCAL,
          // urlList: [''],
          isDfs: false,
        }}
      >
        <Form.Item
          noStyle
          shouldUpdate={(prev, next) =>
            prev.dataSourceType !== next.dataSourceType
          }
        >
          {() => {
            return (
              <Form.Item
                name="fileList"
                rules={[{ required: true, message: t("knowledge.selectFile") }]}
              >
                <DragUpload
                  disabled={loading}
                  maxCount={300}
                  maxSize={TOTAL_FILE_MAX_SIZE}
                  maxFileSize={SINGLE_FILE_MAX_SIZE}
                  accept={isZipMode ? ZIP_FILE_TYPES : ALLOWED_FILE_TYPES}
                  targetPath={data.targetPath}
                  maxLevel={2}
                  onZipStatusChange={setHasZipError}
                  zipMode={isZipMode}
                  selectDirectory={isDirectoryMode}
                  disableDragFolder={!isDirectoryMode}
                  invalidTypeMessage={
                    isDirectoryMode
                      ? t("knowledge.supportedDocTypes")
                      : isZipMode
                        ? t("knowledge.importZip")
                        : t("knowledge.supportedDocTypes")
                  }
                  invalidDropMessage={
                    isDirectoryMode
                      ? t("knowledge.importFolder")
                      : isZipMode
                        ? t("knowledge.importZip")
                        : t("knowledge.supportedDocTypes")
                  }
                  description={
                    <>
                      {isDirectoryMode
                        ? t("knowledge.supportedFolderImport")
                        : isZipMode
                          ? t("knowledge.supportedZipFile")
                          : t("knowledge.supportedDocTypes")}
                      <br />
                      {isZipMode && (
                        <>
                          {t("knowledge.zipRootOnly")}
                          <br />
                        </>
                      )}
                      {t("knowledge.uploadLimitHint")}
                      <br />
                      {t("knowledge.scannedPdfHint")}
                    </>
                  }
                />
              </Form.Item>
            );
          }}
        </Form.Item>
        <Form.Item
          name="tags"
          label={t("knowledge.tags")}
        >
          <TagSelect tags={tags} />
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default forwardRef(ImportKnowledgeModal);

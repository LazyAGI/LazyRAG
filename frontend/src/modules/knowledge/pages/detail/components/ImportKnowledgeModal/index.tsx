import { Button, Form, message, Modal } from "antd";
import {
  forwardRef,
  Ref,
  useEffect,
  useImperativeHandle,
  useState,
} from "react";

import { DataSourceType } from "@/modules/knowledge/constants/common";
import DragUpload from "../DragUpload";
import batchUpload from "@/modules/knowledge/utils/batchUpload";
import {
  DocumentServiceApi,
  JobServiceApi,
} from "@/modules/knowledge/utils/request";
import TagSelect from "@/modules/knowledge/components/TagSelect";
import {
  JobDataSourceTypeEnum,
  JobJobStateEnum,
  StartJobRequestStartModeEnum,
} from "@/api/generated/knowledge-client";
import { useDatasetPermissionStore } from "@/modules/knowledge/store/dataset_permission";

const ALLOWED_FILE_TYPES = ["pdf", "docx", "doc"];
const SINGLE_FILE_MAX_SIZE = 500 * 1024 * 1024;
const TOTAL_FILE_MAX_SIZE = 1 * 1024 * 1024 * 1024;
const ZIP_FILE_TYPES = ["zip"];

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
  const [data, setData] = useState<IData>(InitData);
  const [visible, setVisible] = useState(false);
  const [loading, setLoading] = useState(false);
  const [tags, setTags] = useState<string[]>([]);
  const [hasZipError, setHasZipError] = useState(false);
  // 读权限
  const hasOnlyReadPermission = useDatasetPermissionStore((state) =>
    state.hasOnlyReadPermission(),
  );
  // 上传权限
  const hasUploadPermission = useDatasetPermissionStore((state) =>
    state.hasUploadPermission(),
  );
  // 写权限
  const hasWritePermission = useDatasetPermissionStore((state) =>
    state.hasWritePermission(),
  );
  // 是否只有读权限
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

  function submit(values: any) {
    setLoading(true);
    JobServiceApi()
      .jobServiceCreateJob({
        dataset: data.dataset_id,
        job: {
          data_source_type: JobDataSourceTypeEnum.LocalFile,
          document_pid: data.p_id,
          document_tags: values.tags,
          // files: values.urlList.map((url: string) => { return { target_path: url } })
        },
      })
      .then((res) => {
        message.success("创建上传任务成功");
        handleClose();
        onOk();
        const fileList = values.fileList.map((file: any) => ({
          ...file,
          taskId: res.data.job_id,
        }));
        const task = {
          datasetId: data.dataset_id,
          id: res.data.job_id,
          taskState: JobJobStateEnum.Creating,
        };
        let startMode;
        if (hasWritePermission) {
          startMode = StartJobRequestStartModeEnum.Default;
        } else if (hasUploadPermission) {
          startMode = StartJobRequestStartModeEnum.Upload;
        }
        batchUpload.addTask({ task, fileList, startMode });
      })
      .catch((err) => {
        console.error(err);
      })
      .finally(() => {
        setLoading(false);
      });
  }

  // function changeSourceType() {
  //   form.resetFields(['fileList', 'urlList', 'notionAccount', 'notionPages'])
  // }

  return (
    <Modal
      open={visible}
      destroyOnHidden
      title={"导入文件"}
      onCancel={handleClose}
      centered
      width={896}
      style={{ paddingBottom: 0, minHeight: 300 }}
      className="modal-max-height"
      maskClosable={false}
      footer={
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <Button onClick={handleClose}>{"取消"}</Button>
          <Button
            type="primary"
            disabled={loading || hasZipError}
            onClick={() => form.submit()}
            style={{ marginLeft: 16 }}
          >
            {isOnlyRead ? "上传知识文件" : "解析并导入"}
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
                rules={[{ required: true, message: "请选择文件" }]}
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
                      ? "仅传入pdf、docx、doc格式的文件"
                      : isZipMode
                        ? "请上传zip格式的压缩包"
                        : "请上传pdf、docx、doc格式的文件"
                  }
                  invalidDropMessage={
                    isDirectoryMode
                      ? "请上传文件夹"
                      : isZipMode
                        ? "请上传zip格式的压缩包"
                        : "请上传pdf、docx、doc格式的文件"
                  }
                  description={
                    <>
                      {isDirectoryMode
                        ? "支持导入文件夹"
                        : isZipMode
                          ? "支持zip类型的文件"
                          : "支持pdf、docx、doc类型的文件"}
                      <br />
                      {isZipMode && (
                        <>
                          {
                            "zip压缩包仅支持根目录的文件，一级及以上文件夹将被忽略"
                          }
                          <br />
                        </>
                      )}
                      {
                        "单次上传限制300个文件，单个文件大小不超过500MB，总大小不超过1GB"
                      }
                      <br />
                      {"扫描版pdf单次建议控制在100页以内"}
                    </>
                  }
                />
              </Form.Item>
            );
          }}
        </Form.Item>
        <Form.Item
          name="tags"
          label={"文档标签"}
          // rules={[{ required: true, message: '请选择文档标签' }]}
        >
          <TagSelect tags={tags} />
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default forwardRef(ImportKnowledgeModal);

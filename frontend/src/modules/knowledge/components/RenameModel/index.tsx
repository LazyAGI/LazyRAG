import { forwardRef, useEffect, useImperativeHandle, useState } from "react";
import { Modal, Form, Input, Select } from "antd";
import { useTranslation } from "react-i18next";
import { DocumentServiceApi } from "@/modules/knowledge/utils/request";

export interface IFormLabel {
  name: string;
  namePlaceholder: string;
  nameLen: number;
  nameRules: any[];
  nameAdd?: string;
}

export interface ForwardProps {
  onSubmit: (data: RenameFormItem) => Promise<void>;
}

export interface RenameParamsProps {
  title: string;
  form: IFormLabel;
  data?: RenameFormItem;
}

export interface RenameModalRef {
  onOpen: ({ data }: RenameParamsProps) => void;
}

export interface RenameFormItem {
  name: string;
  tags?: string[];
}

const RenameModel = forwardRef<RenameModalRef, ForwardProps>(
  ({ onSubmit }, ref) => {
    const { t } = useTranslation();
    const [visible, setVisible] = useState(false);
    const [loading, setLoading] = useState(false);
    const [modalInfo, setModalInfo] = useState<
      IFormLabel & { title: string }
    >();
    const [options, setOptions] = useState<string[]>([]);

    const [form] = Form.useForm();

    useImperativeHandle(ref, () => ({
      onOpen,
    }));

    useEffect(() => {
      DocumentServiceApi()
        .documentServiceAllDocumentTags()
        .then((res) => {
          setOptions(res.data.tags);
        });
    }, []);

    const onOpen = (props: RenameParamsProps) => {
      setModalInfo({
        title: props.title,
        ...props.form,
      });
      if (props.data) {
        form.setFieldsValue(props.data);
      }
      setVisible(true);
    };

    const onCancel = () => {
      setVisible(false);
    };

    const onOk = () => {
      form.validateFields().then(async (values) => {
        if (loading) {
          return false;
        }
        setLoading(true);
        try {
          await onSubmit(values);
          setLoading(false);
          onCancel();
        } catch {
          setLoading(false);
        }
      });
    };

    return (
      <Modal
        open={visible}
        destroyOnHidden
        title={modalInfo?.title}
        centered
        onCancel={onCancel}
        onOk={onOk}
        width={576}
        okButtonProps={{ disabled: loading }}
        maskClosable={false}
      >
        <Form form={form} layout="vertical" initialValues={{ name: "" }}>
          <Form.Item
            name="name"
            label={modalInfo?.name}
            rules={modalInfo?.nameRules}
            required
          >
            <Input
              placeholder={modalInfo?.namePlaceholder}
              maxLength={modalInfo?.nameLen}
              addonAfter={modalInfo?.nameAdd}
            />
          </Form.Item>
          {modalInfo?.nameAdd && (
            <Form.Item name="tags" label={t("knowledge.tags")}>
              <Select
                mode="tags"
                tokenSeparators={[","]}
                options={options.map((option) => {
                  return { value: option, label: option };
                })}
              />
            </Form.Item>
          )}
        </Form>
      </Modal>
    );
  },
);

export default RenameModel;

import { Modal, Button } from "antd";
import type { ButtonProps } from "antd";
import { useTranslation } from "react-i18next";

interface CommonModalProps {
  contentText: React.ReactNode;
  title: React.ReactNode;
  successFn?: () => void;
  cancelFn?: () => void;
  isBtn?: boolean;
  width?: number;
  loading?: boolean;
  confirmText?: string;
  cancelText?: string;
  btnType?: ButtonProps["type"];
  disable?: boolean;
}

export default function CommonModal(props: CommonModalProps) {
  const { t } = useTranslation();
  const {
    contentText,
    successFn,
    cancelFn,
    title,
    isBtn = true,
    width = 420,
    loading = false,
    cancelText = t("common.cancel"),
    confirmText = t("common.confirm"),
    btnType = "primary",
    disable = false,
  } = props;

  return (
    <Modal
      footer={
        isBtn ? (
          <>
            <Button key="cancel" onClick={cancelFn} disabled={disable}>
              {cancelText}
            </Button>
            <Button
              type={btnType}
              onClick={successFn}
              loading={loading}
              disabled={disable}
            >
              {confirmText}
            </Button>
          </>
        ) : null
      }
      width={width}
      getContainer={false}
      title={title}
      centered
      onCancel={cancelFn}
      open
      maskClosable={false}
    >
      {contentText}
    </Modal>
  );
}

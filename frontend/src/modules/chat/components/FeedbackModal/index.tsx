import { useState, useEffect } from "react";
import { Modal, Button, Input, Space, message } from "antd";
import { CloseOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import "./index.scss";

const { TextArea } = Input;

interface FeedbackModalProps {
  visible: boolean;
  onCancel: () => void;
  onSubmit: (reason: string[], comment: string) => void;
  
  submitLoading?: boolean;
}

const FEEDBACK_OPTION_IDS = [
  "didNotUnderstand",
  "didNotCompleteTask",
  "fabricatedFacts",
  "tooVerbose",
  "notCreative",
  "poorWritingStyle",
  "outdatedInfo",
  "other",
] as const;

const FeedbackModal = ({
  visible,
  onCancel,
  onSubmit,
  submitLoading = false,
}: FeedbackModalProps) => {
  const { t } = useTranslation();
  const feedbackOptions = FEEDBACK_OPTION_IDS.map((id) => ({
    id,
    label: t(`chatFeedback.${id}`),
  }));
  const [selectedReasons, setSelectedReasons] = useState<string[]>([]);
  const [comment, setComment] = useState("");

  useEffect(() => {
    if (!visible) {
      setSelectedReasons([]);
      setComment("");
    }
  }, [visible]);

  const handleReasonClick = (value: string) => {
    if (selectedReasons.includes(value)) {
      setSelectedReasons(selectedReasons.filter((r) => r !== value));
    } else {
      setSelectedReasons([...selectedReasons, value]);
    }
  };

  const handleSubmit = () => {
    if (selectedReasons.length === 0) {
      message.error(t("chat.atLeastOneUnsatisfiedReason"));
      return;
    }
    if (submitLoading) {
      return;
    }
    onSubmit(selectedReasons, comment);
  };

  const handleCancel = () => {
    setSelectedReasons([]);
    setComment("");
    onCancel();
  };

  return (
    <Modal
      open={visible}
      onCancel={handleCancel}
      footer={null}
      closeIcon={<CloseOutlined />}
      width={720}
      className="feedback-modal"
    >
      <div className="feedback-modal-content">
        <h3 className="feedback-title">{t("chat.feedbackAskUnsatisfied")}</h3>
        <p className="feedback-subtitle">{t("chat.feedbackSubtitle")}</p>
        <Space wrap className="feedback-options">
          {feedbackOptions.map(({ id, label }) => (
            <Button
              key={id}
              type={selectedReasons.includes(label) ? "primary" : "default"}
              onClick={() => handleReasonClick(label)}
              className="feedback-option-btn"
            >
              {label}
            </Button>
          ))}
        </Space>

        <div className="feedback-comment">
          <TextArea
            placeholder={t("chat.expectedAnswer")}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            rows={6}
            maxLength={200}
            showCount={{
              formatter: ({ count, maxLength }) => `${count}/${maxLength}`,
            }}
          />
        </div>

        <div className="feedback-actions">
          <Button onClick={handleCancel} disabled={submitLoading}>
            {t("common.cancel")}
          </Button>
          <Button
            type="primary"
            onClick={handleSubmit}
            loading={submitLoading}
            disabled={submitLoading}
          >
            {t("chat.submitFeedback")}
          </Button>
        </div>
      </div>
    </Modal>
  );
};

export default FeedbackModal;

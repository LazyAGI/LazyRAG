import { useState, useEffect } from "react";
import { Modal, Button, Input, Space, message } from "antd";
import { CloseOutlined } from "@ant-design/icons";
import "./index.scss";

const { TextArea } = Input;

interface FeedbackModalProps {
  visible: boolean;
  onCancel: () => void;
  onSubmit: (reason: string[], comment: string) => void;
  /** 提交中时禁用提交按钮，防止重复提交 */
  submitLoading?: boolean;
}

const FEEDBACK_OPTIONS = [
  "没有理解问题",
  "没有完成任务",
  "编造事实",
  "废话太多",
  "没有创意",
  "文风不好",
  "信息陈旧",
  "其它",
];

const FeedbackModal = ({
  visible,
  onCancel,
  onSubmit,
  submitLoading = false,
}: FeedbackModalProps) => {
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
    // 验证是否至少选择了一个标签
    if (selectedReasons.length === 0) {
      message.error("请至少选择一个不满意的原因");
      return;
    }
    if (submitLoading) {
      return;
    }
    onSubmit(selectedReasons, comment);
    // 不在此处重置表单，等父组件 API 成功/失败后再关闭并重置
  };

  const handleCancel = () => {
    // 重置状态
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
        <h3 className="feedback-title">你觉得什么让你不满意？</h3>
        <p className="feedback-subtitle">请选择理由帮助我们做得更好</p>
        <Space wrap className="feedback-options">
          {FEEDBACK_OPTIONS.map((option: string) => (
            <Button
              key={option}
              type={selectedReasons.includes(option) ? "primary" : "default"}
              onClick={() => handleReasonClick(option)}
              className="feedback-option-btn"
            >
              {option}
            </Button>
          ))}
        </Space>

        <div className="feedback-comment">
          <TextArea
            placeholder="你期望的回答"
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
            取消
          </Button>
          <Button
            type="primary"
            onClick={handleSubmit}
            loading={submitLoading}
            disabled={submitLoading}
          >
            提交反馈
          </Button>
        </div>
      </div>
    </Modal>
  );
};

export default FeedbackModal;

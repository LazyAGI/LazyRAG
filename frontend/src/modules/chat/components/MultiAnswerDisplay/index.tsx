import { useState, useEffect } from "react";
import { Space, Radio } from "antd";
import type { RadioChangeEvent } from "antd";
import "./index.scss";

export interface Answer {
  content: string;
  index: number;
  history_id?: string; // 每个回答都有独立的 history_id
  reasoning_content?: string; // 每个回答都有独立的思考过程
  sources?: any[]; // 每个回答都有独立的知识库来源
  thinking_duration_s?: string; // 每个回答都有独立的思考时间
}

export type PreferenceType =
  | "prefer_first"
  | "prefer_second"
  | "similar"
  | "neither";

interface MultiAnswerDisplayProps {
  answers: Answer[];
  renderText: (
    content: string,
    reasoningContent?: string,
    answerIndex?: number,
  ) => React.ReactNode; // 添加 answerIndex 参数
  onSelectAnswer?: (selectedIndex: number, preference: PreferenceType) => void;
  disabled?: boolean;
  renderFooter?: (
    answerIndex: number,
    showFullToolbar: boolean,
  ) => React.ReactNode; // 为每个回答渲染操作按钮
  renderKnowledgeBase?: (answerIndex: number) => React.ReactNode; // 🆕 为每个回答渲染知识库来源
  initialSelectedIndex?: number; // 🆕 初始选中的回答索引（从历史数据中恢复）
  initialPreference?: PreferenceType; // 🆕 初始的偏好选择
  isStreaming?: boolean; // 🆕 是否正在流式输出
  showPreference?: boolean; // 🆕 是否显示回答偏好（仅最新双模型回答显示）
}

const MultiAnswerDisplay: React.FC<MultiAnswerDisplayProps> = ({
  answers,
  renderText,
  onSelectAnswer,
  disabled = false,
  renderFooter,
  renderKnowledgeBase,
  initialSelectedIndex,
  initialPreference,
  isStreaming = false,
  showPreference = true,
}) => {
  const [selectedAnswer, setSelectedAnswer] = useState<number | null>(
    initialSelectedIndex ?? null,
  );
  const [preference, setPreference] = useState<PreferenceType | null>(
    initialPreference ?? null,
  );

  // 🆕 当 props 变化时同步到 state
  useEffect(() => {
    if (initialSelectedIndex !== undefined) {
      setSelectedAnswer(initialSelectedIndex);
    }
  }, [initialSelectedIndex]);

  useEffect(() => {
    if (initialPreference !== undefined) {
      setPreference(initialPreference);
    }
  }, [initialPreference]);

  if (!answers || answers.length < 2) {
    return null;
  }

  const handlePreferenceChange = (e: RadioChangeEvent) => {
    const newPreference = e.target.value;
    setPreference(newPreference);

    if (newPreference === "prefer_first") {
      setSelectedAnswer(0);
      onSelectAnswer?.(0, newPreference);
    } else if (newPreference === "prefer_second") {
      setSelectedAnswer(1);
      onSelectAnswer?.(1, newPreference);
    } else if (newPreference === "similar" || newPreference === "neither") {
      // 两者差不多或都不好时，默认选择回答1
      setSelectedAnswer(0);
      onSelectAnswer?.(0, newPreference);
    }
  };

  // 如果用户已经选择了某个回答，则只显示选中的回答
  if (selectedAnswer !== null) {
    const selectedAnswerData = answers[selectedAnswer];
    return (
      <div className="multi-answer-container">
        {/* 选中的回答 - 不显示标题和标签 */}
        <div className="selected-answer">
          <div className="answer-content">
            {renderText(
              selectedAnswerData.content,
              selectedAnswerData.reasoning_content,
              selectedAnswer,
            )}
          </div>

          {/* 🆕 显示知识库来源 */}
          {renderKnowledgeBase && renderKnowledgeBase(selectedAnswer)}

          {/* 该回答的操作按钮 - 显示完整工具栏 */}
          {renderFooter && renderFooter(selectedAnswer, true)}
        </div>
      </div>
    );
  }
  return (
    <div className="multi-answer-container">
      {/* 两个回答内容 */}
      <div className={`answers-wrapper ${isStreaming ? "streaming" : ""}`}>
        {answers.map((answer, index) => (
          <div
            key={answer.history_id || index}
            className={`answer-item ${selectedAnswer === index ? "selected" : ""}`}
          >
            <div className="answer-header">
              <span className="answer-label">
                {index === 0 ? "LazyRAG 大模型" : "DeepSeek"}
              </span>
            </div>
            <div className="answer-content">
              {/* 渲染每个回答的独立思考过程和内容，传入 index 作为唯一标识 */}
              {renderText(answer.content, answer.reasoning_content, index)}
            </div>

            {/* 🆕 显示知识库来源 */}
            {renderKnowledgeBase && index === 0 && renderKnowledgeBase(index)}

            {/* 每个回答的操作按钮 - 只显示复制按钮 */}
            {renderFooter && renderFooter(index, false)}
          </div>
        ))}
      </div>

      {/* 选择区域移到底部 - 仅最新双模型回答显示 */}
      {!disabled && showPreference && (
        <div className="preference-section-bottom">
          <div className="preference-title">您更偏好哪个版本的回答？</div>
          <Radio.Group
            onChange={handlePreferenceChange}
            value={preference}
            buttonStyle="solid"
          >
            <Space size="middle">
              <Radio.Button value="prefer_first">LazyRAG 大模型</Radio.Button>
              <Radio.Button value="prefer_second">DeepSeek</Radio.Button>
              <Radio.Button value="similar">都挺好</Radio.Button>
              <Radio.Button value="neither">都不好</Radio.Button>
            </Space>
          </Radio.Group>
        </div>
      )}
    </div>
  );
};

export default MultiAnswerDisplay;

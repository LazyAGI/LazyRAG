import { type ChangeEvent, type KeyboardEvent, type ReactNode, type Ref } from "react";
import { Input, Typography } from "antd";
import { ClockCircleFilled, MessageOutlined } from "@ant-design/icons";
import {
  type SelfEvolutionChatMessage,
  type SelfEvolutionCheckpointPrompt,
} from "./types";

const { Paragraph, Text } = Typography;

type ChatMessageStreamProps = {
  messages: SelfEvolutionChatMessage[];
  streamRef: Ref<HTMLDivElement>;
};

export function ChatMessageStream({ messages, streamRef }: ChatMessageStreamProps) {
  return (
    <div
      ref={streamRef}
      className="self-evolution-chat-stream"
      aria-live="polite"
      aria-label="会话消息流"
    >
      {messages.length > 0 ? (
        messages.map((item) => (
          <article key={item.id} className={`self-evolution-bubble is-${item.role}`}>
            {item.agentLabel && (
              <Text className="self-evolution-bubble-agent-label">{item.agentLabel}</Text>
            )}
            <Paragraph>{item.content}</Paragraph>
            <Text>{item.time}</Text>
          </article>
        ))
      ) : (
        <Paragraph className="self-evolution-chat-empty">
          当前会话暂无消息，请在底部输入指令开始。
        </Paragraph>
      )}
    </div>
  );
}

type ChatComposerProps = {
  activeStepText: string;
  isAutoInteractionActive: boolean;
  isSendingMessage: boolean;
  pendingCheckpointWaitPrompt?: SelfEvolutionCheckpointPrompt;
  prompt: string;
  onPromptChange: (value: string) => void;
  onSend: (command?: string) => void;
  renderKnowledgeAndModeTools: () => ReactNode;
  renderSendButton: () => ReactNode;
};

export function ChatComposer({
  activeStepText,
  isAutoInteractionActive,
  isSendingMessage,
  pendingCheckpointWaitPrompt,
  prompt,
  onPromptChange,
  onSend,
  renderKnowledgeAndModeTools,
  renderSendButton,
}: ChatComposerProps) {
  const onInputChange = (event: ChangeEvent<HTMLTextAreaElement>) => {
    onPromptChange(event.target.value);
  };

  const onInputPressEnter = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.shiftKey) {
      return;
    }
    event.preventDefault();
    if (prompt.trim()) {
      onSend();
    }
  };
  const isCheckpointWaiting = Boolean(pendingCheckpointWaitPrompt);

  return (
    <div className={`self-evolution-chat-composer${isAutoInteractionActive ? " is-auto" : ""}`}>
      {pendingCheckpointWaitPrompt && (
        <div
          className={`self-evolution-checkpoint-wait${
            pendingCheckpointWaitPrompt.kind === "failure" ? " is-failure" : ""
          }`}
          role="status"
          aria-live="polite"
        >
          <div className="self-evolution-checkpoint-wait-icon">
            <ClockCircleFilled />
          </div>
          <div className="self-evolution-checkpoint-wait-content">
            <Paragraph className="self-evolution-checkpoint-wait-message">
              {pendingCheckpointWaitPrompt.message}
            </Paragraph>
          </div>
          <button
            type="button"
            className="self-evolution-checkpoint-wait-command"
            onClick={() => onSend(pendingCheckpointWaitPrompt.command)}
            disabled={isSendingMessage}
          >
            {isSendingMessage
              ? pendingCheckpointWaitPrompt.command === "重试"
                ? "重试中..."
                : "继续中..."
              : pendingCheckpointWaitPrompt.command}
          </button>
        </div>
      )}

      {isAutoInteractionActive && !isCheckpointWaiting ? (
        <div className="self-evolution-auto-interaction-status" role="status" aria-live="polite">
          <MessageOutlined />
          <Text>自动交互进行中，模拟用户与回复 Agent 的消息会展示在上方对话流。</Text>
        </div>
      ) : (
        <>
          <Input.TextArea
            value={prompt}
            onChange={onInputChange}
            autoSize={{ minRows: 2, maxRows: 4 }}
            className="self-evolution-chatlike-input"
            placeholder="继续输入指令，例如：请先扩展数据集样本，再进入评测阶段。"
            aria-label="继续输入自进化指令"
            onPressEnter={onInputPressEnter}
          />

          <div className="self-evolution-chat-composer-footer">
            <div className="self-evolution-chat-composer-left">
              {renderKnowledgeAndModeTools()}
            </div>

            <div className="self-evolution-chatlike-actions">
              <Text className="self-evolution-chatlike-helper">
                {isSendingMessage ? "消息发送中" : activeStepText}
              </Text>
              {renderSendButton()}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

import React, { useRef } from "react";
import { RoleTypes } from "@/modules/chat/constants/common";
import AssistantMessage from "../../AssistantMessage";
import type { PreferenceType } from "../../MultiAnswerDisplay";
import "../index.scss";
import dayjs from "dayjs";

interface MessageListProps {
  messageList: any[];
  initialCard?: React.ReactElement | string;
  sendMessage: (text: string, clearInput?: boolean) => void;
  regenerate: () => void;
  stopGeneration: () => void;
  renderText: (item: any) => React.ReactNode;
  updateAssistantMessage: (data: any, id?: string, index?: number) => void;
  onScroll?: () => void;
  chatContentRef?: React.RefObject<HTMLDivElement>;
  sessionId?: string;
  onPreferenceSelect?: (preference: PreferenceType, sessionId?: string) => void;
}

const MessageList: React.FC<MessageListProps> = ({
  messageList,
  initialCard,
  sendMessage,
  regenerate,
  stopGeneration,
  renderText,
  updateAssistantMessage,
  onScroll,
  chatContentRef,
  sessionId = "",
  onPreferenceSelect,
}) => {
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  const contentRef = chatContentRef || scrollContainerRef;

  const renderUser = (item: any) => {
    return (
      <div className="user-message-row">
        {item.create_time && (
          <div className="chat-time">
            {dayjs(item.create_time).format("MM/DD HH:mm")}
          </div>
        )}
        <div className="user-wrap">
          <div className="chat-user">{renderText(item)}</div>
        </div>
      </div>
    );
  };

  return (
    <div
      className="message-container chat-content"
      style={{ flex: messageList.length > 0 ? 1 : undefined }}
      ref={contentRef}
      onScroll={onScroll}
    >
      {messageList.length > 0 &&
        messageList.map((item, index) => {
          return (
            <div className="chat-item" key={`chat-${index}`}>
              {item.role === RoleTypes.USER && renderUser(item)}
              {item.role === RoleTypes.ASSISTANT && (
                <AssistantMessage
                  item={item}
                  index={index}
                  length={messageList.length}
                  sendMessage={sendMessage}
                  regenerate={regenerate}
                  stopGeneration={stopGeneration}
                  renderText={renderText}
                  updateMessage={(msg: any) =>
                    updateAssistantMessage(msg, msg.id || msg.history_id, index)
                  }
                  sessionId={sessionId}
                  onPreferenceSelect={onPreferenceSelect}
                  isLatestDualAnswer={
                    index === messageList.length - 1 &&
                    !!(
                      item.answers &&
                      Array.isArray(item.answers) &&
                      item.answers.length >= 2
                    )
                  }
                />
              )}
            </div>
          );
        })}

      {messageList.length === 0 && initialCard}
    </div>
  );
};

export default MessageList;

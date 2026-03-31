import { useState, useEffect, useRef } from "react";
import "./index.scss";
import DisclaimerIcon from "../../assets/icons/disclaimer_icon.svg?react";
import WarningIcon from "../../assets/icons/warning.svg?react";
import ChatInput, {
  ChatInputImperativeProps,
} from "@/modules/chat/components/ChatInput";
import ChatLayout from "../chatLayout";
import { ChatConfig } from "@/modules/chat/components/ChatConfigs";
import { Tooltip, message } from "antd";
import { CHAT_RESUME_CONVERSATION_KEY } from "@/modules/chat/constants/chat";
import { allowedUploadTypes } from "@/modules/chat/components/ImageUpload";
import { useTranslation } from "react-i18next";

const NewChatPage = () => {
  const { t } = useTranslation();
  const getGreeting = () => {
    const currentHour = new Date().getHours();
    return currentHour < 12 ? t("chat.greetingMorning") : t("chat.greetingAfternoon");
  };
  const [inputValue, setInputValue] = useState("");
  const [isChatContent, setIsChatContent] = useState(false);
  const [chatConfig, setChatConfig] = useState<ChatConfig>({});
  const [chatLayoutMounted, setChatLayoutMounted] = useState(false);
  const newChatInputRef = useRef<ChatInputImperativeProps>(null);

  const [isDragging, setIsDragging] = useState(false);
  const dragCounterRef = useRef(0);

  useEffect(() => {
    if (!isChatContent) {
      newChatInputRef.current?.clearFiles();
      setInputValue("");
    }
  }, [isChatContent]);

  const handleSetIsChatContent = (value: boolean) => {
    if (value && !chatLayoutMounted) {
      setChatLayoutMounted(true);
    }
    setIsChatContent(value);
  };

  useEffect(() => {
    if (
      sessionStorage.getItem(CHAT_RESUME_CONVERSATION_KEY) &&
      !chatLayoutMounted
    ) {
      setChatLayoutMounted(true);
      setIsChatContent(true);
    }
  }, [chatLayoutMounted]);

  const isFileTypeSupported = (file: File): boolean => {
    const ext = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
    return allowedUploadTypes.includes(ext);
  };

  const handleDragEnter = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current++;
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      setIsDragging(true);
    }
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current--;
    if (dragCounterRef.current === 0) {
      setIsDragging(false);
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    dragCounterRef.current = 0;

    const files = Array.from(e.dataTransfer.files);

    if (files.length === 0) {
      return;
    }

    const unsupportedFiles = files.filter((file) => !isFileTypeSupported(file));

    if (unsupportedFiles.length > 0) {
      message.error(t("chat.unsupportedFileTypeDrag"));
      return;
    }

    newChatInputRef.current?.uploadFiles(files);
  };

  return (
    <div>
      {}
      {chatLayoutMounted && (
        <div style={{ display: isChatContent ? "block" : "none" }}>
          <ChatLayout
            setIsChatContent={handleSetIsChatContent}
            setChatConfigFn={setChatConfig}
            initchatConfig={chatConfig}
          />
        </div>
      )}
      <div
        style={{ display: isChatContent ? "none" : "block" }}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      >
        <div className="new-chat-container">
          {}
          {isDragging && (
            <div className="drag-overlay">
              <div className="drag-overlay-content">
                <div className="drag-icon">📁</div>
                <div className="drag-text">{t("chat.dragToUpload")}</div>
                <div className="drag-hint">{t("chat.dragSupportedFormats")}</div>
              </div>
            </div>
          )}
          <div className="new-chat-main">
            <div className="chat-content-container">
              <div className="bg"></div>
              <div className="chat-content">
                <div className="greeting-section">
                  <h1 className="greeting-text">
                    {getGreeting()}{t("chat.greetingSuffix")}
                  </h1>
                </div>

                <div className="input-section">
                  <ChatInput
                    ref={newChatInputRef}
                    value={inputValue}
                    onChange={setInputValue}
                    openHistory={() => handleSetIsChatContent(true)}
                    openNewChat={() => handleSetIsChatContent(false)}
                    isChatContent={isChatContent}
                    showHistoryList={false}
                    setIsChatContent={(value) => {
                      if (value) {
                        setInputValue("");
                      }
                      handleSetIsChatContent(value);
                    }}
                    chatConfig={chatConfig}
                    setChatConfig={setChatConfig}
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="disclaimer-section">
            <div className="tip-box">
              <DisclaimerIcon />
              <span className="disclaimer-text">
                {t("chat.disclaimerAI")}
              </span>
            </div>
            <div className="tip-box">
              <WarningIcon />
              <span className="disclaimer-text">
                {t("chat.disclaimerSecurity")}
                <Tooltip title={<span>{t("chat.disclaimerTooltip")}</span>}>
                  <span style={{ cursor: "pointer", marginLeft: 4 }}>
                    {t("chat.disclaimerSensitive")}
                  </span>
                </Tooltip>
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default NewChatPage;

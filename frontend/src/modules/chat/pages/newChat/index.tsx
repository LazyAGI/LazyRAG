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

const getGreeting = () => {
  const currentHour = new Date().getHours();
  return currentHour < 12 ? "上午好" : "下午好";
};


const NewChatPage = () => {
  const [inputValue, setInputValue] = useState("");
  const [isChatContent, setIsChatContent] = useState(false);
  const [chatConfig, setChatConfig] = useState<ChatConfig>({});
  // 用于跟踪ChatLayout是否已经被挂载过（懒加载优化）
  const [chatLayoutMounted, setChatLayoutMounted] = useState(false);
  const newChatInputRef = useRef<ChatInputImperativeProps>(null);

  // 拖拽相关状态
  const [isDragging, setIsDragging] = useState(false);
  const dragCounterRef = useRef(0);

  // 监听 isChatContent 变化，当切换回新建对话页面时清空文件
  useEffect(() => {
    if (!isChatContent) {
      // 切换回新建对话页面，清空该页面 ChatInput 的文件
      newChatInputRef.current?.clearFiles();
      setInputValue("");
    }
  }, [isChatContent]);

  // 当首次进入对话模式时，标记ChatLayout已挂载
  const handleSetIsChatContent = (value: boolean) => {
    if (value && !chatLayoutMounted) {
      setChatLayoutMounted(true);
    }
    setIsChatContent(value);
  };

  // 刷新后续传：如有生成中的会话，提前挂载 ChatLayout 以便恢复
  useEffect(() => {
    if (
      sessionStorage.getItem(CHAT_RESUME_CONVERSATION_KEY) &&
      !chatLayoutMounted
    ) {
      setChatLayoutMounted(true);
      setIsChatContent(true);
    }
  }, [chatLayoutMounted]);

  // 检查文件类型是否支持
  const isFileTypeSupported = (file: File): boolean => {
    const ext = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
    return allowedUploadTypes.includes(ext);
  };

  // 处理拖拽进入
  const handleDragEnter = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current++;
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      setIsDragging(true);
    }
  };

  // 处理拖拽离开
  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current--;
    if (dragCounterRef.current === 0) {
      setIsDragging(false);
    }
  };

  // 处理拖拽悬停
  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
  };

  // 处理文件放置
  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    dragCounterRef.current = 0;

    const files = Array.from(e.dataTransfer.files);

    if (files.length === 0) {
      return;
    }

    // 检查是否有不支持的文件类型
    const unsupportedFiles = files.filter((file) => !isFileTypeSupported(file));

    if (unsupportedFiles.length > 0) {
      message.error("不支持上传该类型文件");
      return;
    }

    // 调用 ChatInput 的 uploadFiles 方法
    newChatInputRef.current?.uploadFiles(files);
  };

  return (
    <div>
      {/* ChatLayout一旦挂载就不再卸载，用CSS控制显示/隐藏，避免组件卸载导致SSE连接中断 */}
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
          {/* 拖拽蒙层 */}
          {isDragging && (
            <div className="drag-overlay">
              <div className="drag-overlay-content">
                <div className="drag-icon">📁</div>
                <div className="drag-text">文件拖动到此处即可上传</div>
                <div className="drag-hint">
                  支持的文件格式：PDF、Word文档（DOC、DOCX）、PPTX、图片（PNG、JPG）
                </div>
              </div>
            </div>
          )}
          <div className="new-chat-main">
            <div className="chat-content-container">
              <div className="bg"></div>
              <div className="chat-content">
                <div className="greeting-section">
                  <h1 className="greeting-text">
                    {getGreeting()}，有什么我能帮你的吗？
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
                AI 生成内容不代表开发者立场
              </span>
            </div>
            <div className="tip-box">
              <WarningIcon />
              <span className="disclaimer-text">
                为了保障您的信息安全，请勿上传
                <Tooltip
                  title={
                    <span>
                      风险提示：为了保障您的信息安全，请勿上传
                      <span style={{ color: "#FFA73A" }}>
                        敏感个人信息（如您的密码等信息）和您的敏感资产信息（如关键源代码、签名私钥、调试安装包、业务日志等信息），
                      </span>
                      且您需自行承担由此产生的信息泄露等安全风险。
                    </span>
                  }
                >
                  <span style={{ cursor: "pointer", marginLeft: 4 }}>
                    敏感个人信息
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

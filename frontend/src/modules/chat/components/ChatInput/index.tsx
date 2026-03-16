import {
  useState,
  useRef,
  forwardRef,
  useEffect,
  useCallback,
  useImperativeHandle,
  useMemo,
} from "react";
import { RcFile } from "antd/es/upload";
import { Button, Input, Tooltip, message } from "antd";
import { debounce } from "lodash";
import AttachmentIcon from "../../assets/icons/attachment_icon.svg?react";
import SendIcon from "../../assets/icons/send_icon.svg?react";
import AddIcon from "../../assets/icons/add.svg?react";
import BatchChatIcon from "../../assets/icons/batch_chat.svg?react";

import ImageUpload, {
  allowedImageTypes,
  allowedFileTypes,
  allowedUploadTypes,
  ImageUploadImperativeProps,
  OnBeforeAddFilesResult,
} from "../ImageUpload";
import { fileToBase64 } from "@/modules/chat/utils/upload";
import { useChatMessageStore } from "@/modules/chat/store/chatMessage";
import { useChatInputStore } from "@/modules/chat/store/chatInput";

import "./index.scss";

import { ChatConfig } from "../ChatConfigs";
import ChatSelector from "../ChatSelector";
import PromptModal, { PromptImperativeProps } from "../PromptModal";
import BatchChatComponent, { BatchChatImperativeProps } from "../BatchChat";
import ModelSelector from "../ModelSelector";
import ShowChatFileList from "../ShowChatFileList";
import { formatFileSize } from "@/modules/chat/utils";
import { useChatThinkStore } from "@/modules/chat/store/chatThink";
import { useChatNewMessageStore } from "@/modules/chat/store/chatNewMessage";

const { TextArea } = Input;

const TOAST_PRIORITY_FILE = "本次回答将优先基于上传的文件进行回答";
const TOAST_DOC_IMAGE_EXCLUSIVE = "不支持同时传入文档与图片";

function getSuffix(f: { name: string }) {
  return f.name.substring(f.name.lastIndexOf(".")).toLowerCase();
}
function isImage(f: { name: string }) {
  return allowedImageTypes.includes(getSuffix(f));
}
function isDoc(f: { name: string }) {
  return allowedFileTypes.includes(getSuffix(f));
}

/** 上传前预处理：文档/图片互斥、Toast。不修改知识库选择。 */
function preprocessUpload(
  newFiles: File[],
  currentFiles: { name: string }[],
  hasKB: boolean,
): OnBeforeAddFilesResult {
  const hasImage = currentFiles.some(isImage);
  const hasDoc = currentFiles.some(isDoc);
  const newImages = newFiles.filter((f) => isImage(f));
  const newDocs = newFiles.filter((f) => isDoc(f));
  const newHasBoth = newImages.length > 0 && newDocs.length > 0;

  let filesToAdd: File[];
  let clearFirst: boolean;
  const toasts: string[] = [];

  if (newHasBoth) {
    filesToAdd = newDocs;
    clearFirst = currentFiles.length > 0;
    toasts.push(TOAST_DOC_IMAGE_EXCLUSIVE);
    if (hasKB) {
      toasts.push(TOAST_PRIORITY_FILE);
    }
  } else if (hasDoc && newImages.length > 0) {
    // 已有文档再传图片：仅提示，不替换、不添加
    clearFirst = false;
    filesToAdd = [];
    toasts.push(TOAST_DOC_IMAGE_EXCLUSIVE);
    if (hasKB) {
      toasts.push(TOAST_PRIORITY_FILE);
    }
  } else if (hasImage && newDocs.length > 0) {
    // 已有图片再传文档：仅提示，不替换、不添加
    clearFirst = false;
    filesToAdd = [];
    toasts.push(TOAST_DOC_IMAGE_EXCLUSIVE);
    if (hasKB) {
      toasts.push(TOAST_PRIORITY_FILE);
    }
  } else {
    clearFirst = false;
    filesToAdd = newFiles;
    if (hasKB && newFiles.length > 0) {
      toasts.push(TOAST_PRIORITY_FILE);
    }
  }

  return { filesToAdd, clearFirst, toasts };
}

export interface SendMessageParams {
  text: string;
  clearInput?: boolean;
  fileList?: ChatFileList[];
  fileListRef?: React.RefObject<ImageUploadImperativeProps | null>;
  files?: (RcFile & { uri: string })[];
  create_time?: string;
}

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSend?: (params: SendMessageParams) => void;
  placeholder?: string;
  openHistory: () => void;
  openNewChat?: () => void;
  isChatContent: boolean;
  showHistoryList: boolean;
  setIsChatContent?: (isChatContent: boolean) => void;
  onHeightChange?: () => void;
  chatConfig?: ChatConfig;
  setChatConfig?: (chatConfig: ChatConfig) => void;
  setChatConfigFn?: (chatConfig: ChatConfig) => void;
  sessionId?: string; // 当前会话ID，用于暂存和恢复输入内容
  isStreaming?: boolean; // 流式输出时禁用模型选择
}

export interface ChatFileList {
  uid: string;
  name: string;
  base64: string;
  suffix: string;
  size: string;
}

export interface ChatInputImperativeProps {
  clearFiles: () => void;
  element: HTMLDivElement | null;
  uploadFiles: (files: File[]) => void;
}

interface SendIconProps {
  disabled: boolean;
  onClick: () => void;
}
const SendButton: React.FC<SendIconProps> = ({ disabled, onClick }) => {
  return (
    <div
      className={`send-button ${disabled ? "disabled" : ""}`}
      onClick={onClick}
    >
      <SendIcon />
    </div>
  );
};

SendButton.displayName = "SendButton";

const ChatInput = forwardRef<ChatInputImperativeProps, ChatInputProps>(
  (props, ref) => {
    const {
      value,
      onChange,
      onSend,
      placeholder,
      openHistory,
      openNewChat,
      isChatContent,
      showHistoryList,
      onHeightChange,
      setIsChatContent,
      chatConfig,
      setChatConfig,
      setChatConfigFn,
      sessionId,
      isStreaming = false,
    } = props;
    const fileListRef = useRef<ImageUploadImperativeProps | null>(null);
    const promptRef = useRef<PromptImperativeProps>(null);
    const batchChatRef = useRef<BatchChatImperativeProps | null>(null);
    const innerRef = useRef<HTMLDivElement>(null);
    const [isUploading, setIsUploading] = useState(false);
    const { setThink } = useChatThinkStore();
    const { setNewMessage } = useChatNewMessageStore();
    const [text, setText] = useState("");
    const previousSessionIdRef = useRef<string | undefined>(undefined);
    // 标记消息已发送，用于在 effect cleanup 时跳过保存
    const hasSentMessageRef = useRef(false);

    const [fileList, setFileList] = useState<ChatFileList[]>([]);
    const { setPendingMessage, clearPendingMessage } = useChatMessageStore();
    const { saveInputContent, getInputContent, clearInputContent } =
      useChatInputStore();

    // 使用 lodash 的 debounce 创建防抖保存函数
    const debouncedSaveInput = useMemo(
      () =>
        debounce((conversationId: string, content: string) => {
          // 如果内容为空，则从 store 中移除该会话的存储对象
          if (!content || content.trim() === "") {
            clearInputContent(conversationId);
          } else {
            saveInputContent(conversationId, content);
          }
        }, 500),
      [saveInputContent, clearInputContent],
    );

    const clearMultiData = useCallback(() => {
      setFileList([]);
      fileListRef.current?.clear();
      // 通知父组件高度可能已变化
      setTimeout(() => onHeightChange?.(), 0);
    }, [onHeightChange]);

    // 暴露清理文件的方法和 DOM 元素给父组件
    useImperativeHandle(
      ref,
      () => ({
        clearFiles: () => {
          clearMultiData();
          clearPendingMessage(); // 同时清空 store 中的待发送消息
        },
        element: innerRef.current,
        uploadFiles: (files: File[]) => {
          fileListRef.current?.uploadFiles(files);
        },
      }),
      [clearPendingMessage, clearMultiData],
    );

    // 监听 sessionId 变化，从 store 恢复输入内容
    useEffect(() => {
      if (
        sessionId !== undefined &&
        sessionId !== previousSessionIdRef.current
      ) {
        const previousId = previousSessionIdRef.current;

        // 取消防抖，立即保存上一个会话的输入内容
        debouncedSaveInput.cancel();

        // 保存上一个会话的输入内容
        if (previousId !== undefined) {
          // 如果内容为空，则从 store 中移除该会话的存储对象
          const previousValue = value || "";
          if (!previousValue || previousValue.trim() === "") {
            clearInputContent(previousId);
          } else {
            saveInputContent(previousId, previousValue);
          }

          // 如果从临时ID切换到真实ID，将临时ID的内容迁移到真实ID
          if (
            previousId.startsWith("temp_") &&
            !sessionId.startsWith("temp_")
          ) {
            const tempContent = getInputContent(previousId);
            if (tempContent) {
              saveInputContent(sessionId, tempContent);
              clearInputContent(previousId);
            }
          }
        }

        // 恢复当前会话的输入内容
        const savedContent = getInputContent(sessionId);
        if (savedContent !== value) {
          onChange(savedContent);
        }

        previousSessionIdRef.current = sessionId;
      }
    }, [
      sessionId,
      saveInputContent,
      getInputContent,
      clearInputContent,
      onChange,
      value,
      debouncedSaveInput,
    ]);

    // 组件卸载时取消防抖并立即保存当前会话的输入内容
    useEffect(() => {
      return () => {
        // 取消防抖
        debouncedSaveInput.cancel();

        // 如果消息已发送，跳过保存逻辑（内容已在 handleSend 中清理）
        if (hasSentMessageRef.current) {
          hasSentMessageRef.current = false;
          return;
        }

        // 保存或清除当前会话的输入内容
        if (sessionId !== undefined) {
          const currentValue = value || "";
          if (!currentValue || currentValue.trim() === "") {
            clearInputContent(sessionId);
          } else {
            saveInputContent(sessionId, currentValue);
          }
        }
      };
    }, [
      sessionId,
      value,
      saveInputContent,
      clearInputContent,
      debouncedSaveInput,
    ]);

    // 监听上传状态变化
    useEffect(() => {
      const checkUploadStatus = () => {
        const uploadingCount = fileListRef.current?.getUploadingCount() || 0;
        setIsUploading(uploadingCount > 0);
      };

      // 每500毫秒检查一次上传状态
      const interval = setInterval(checkUploadStatus, 500);

      return () => clearInterval(interval);
    }, []);
    const updateImageList = async (list: RcFile[]) => {
      const data: ChatFileList[] = [];
      for (let i = 0; i < list.length; i++) {
        const suffix = list[i].name
          .substring(list[i].name.lastIndexOf("."))
          .toLowerCase();

        const tempImgData = allowedImageTypes.includes(suffix);
        const obj = {
          name: list[i].name,
          uid: list[i].uid,
          suffix,
          size: formatFileSize(list[i].size),
          base64: "",
        };
        if (tempImgData) {
          const res = await fileToBase64(list[i]);
          obj["base64"] = res as string;
        } else {
          obj["base64"] = "";
        }
        data.push(obj);
      }
      setFileList(data);
      // 通知父组件高度可能已变化
      setTimeout(() => onHeightChange?.(), 0);
    };

    const removeImage = (uid: string) => {
      fileListRef.current?.removeFile(uid);
      const list = [...fileList].filter((item) => item.uid !== uid);
      setFileList(list);
      // 通知父组件高度可能已变化
      setTimeout(() => onHeightChange?.(), 0);
    };

    const onKnowledgeBaseChange = (
      knowledgeBaseId: string[],
      creators: string[],
      tags: string[],
    ) => {
      const tempData = { ...chatConfig, knowledgeBaseId, creators, tags };
      setChatConfig?.(tempData);
      setChatConfigFn?.(tempData);

      // 若已有上传文件，且用户从"无知识库"切换到"有知识库"，提示优先使用文件
      const hadNoKB = (chatConfig?.knowledgeBaseId?.length ?? 0) === 0;
      const nowHasKB = knowledgeBaseId.length > 0;
      const hasFiles = fileList.length > 0;
      if (hadNoKB && nowHasKB && hasFiles) {
        message.info(TOAST_PRIORITY_FILE);
      }
    };

    const hasKB = (chatConfig?.knowledgeBaseId?.length ?? 0) > 0;
    const onBeforeAddFiles = useCallback(
      (newFiles: File[], currentFiles: { name: string }[]) =>
        preprocessUpload(newFiles, currentFiles, hasKB),
      [hasKB],
    );

    const handleSend = () => {
      if (!value?.length || isUploading) {
        return;
      }
      setNewMessage(false);
      const sendParams = {
        text: value,
        fileList,
        fileListRef,
        files: fileListRef.current?.getFiles(),
        create_time: new Date().toISOString(),
      };

      if (!isChatContent) {
        // 如果在 newChat 页面，存储消息到 store 并切换到 chatContent 页面
        setPendingMessage(sendParams);
        setIsChatContent?.(true);
      } else {
        // 如果在 chatContent 页面，直接发送消息
        onSend?.(sendParams);
        clearMultiData();
      }

      // 标记消息已发送，用于在 effect cleanup 时跳过保存
      hasSentMessageRef.current = true;

      // 发送消息后，清除当前会话的输入内容（如果提供了 sessionId），并清空输入框
      if (sessionId !== undefined) {
        // 先取消可能尚未执行的防抖保存，以避免再次把旧内容写回本地存储
        debouncedSaveInput.cancel();
        clearInputContent(sessionId);
      }
      // 清空输入框内容
      onChange("");
      setText("");
    };

    // 处理输入框内容变化（带防抖保存）
    const handleInputChange = (text: string) => {
      onChange(text);
      setText(text);
      // 使用 lodash 的 debounce 保存到 store（如果提供了 sessionId）
      if (sessionId !== undefined) {
        debouncedSaveInput(sessionId, text);
      }
    };

    // 处理剪贴板粘贴事件
    const handlePaste = useCallback(
      (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
        const clipboardData = e.clipboardData;
        if (!clipboardData) {
          return;
        }

        const items = clipboardData.items;
        const files: File[] = [];
        const invalidFiles: File[] = [];
        let hasAnyFile = false;

        // 遍历剪贴板项
        for (let i = 0; i < items.length; i++) {
          const item = items[i];

          // 检查是否为文件类型
          if (item.kind === "file") {
            hasAnyFile = true;
            const file = item.getAsFile();
            if (file) {
              // 检查文件扩展名是否在允许的类型中
              const fileName = file.name || `pasted-file-${Date.now()}`;
              const suffix = fileName.includes(".")
                ? fileName.substring(fileName.lastIndexOf(".")).toLowerCase()
                : "";

              // 如果是图片但没有扩展名，根据 MIME 类型添加扩展名
              let finalFile = file;
              if (!suffix && file.type.startsWith("image/")) {
                const ext = file.type.split("/")[1] || "png";
                const newFileName = `pasted-image-${Date.now()}.${ext}`;
                finalFile = new File([file], newFileName, { type: file.type });
              }

              // 检查文件类型是否允许
              const finalSuffix = finalFile.name
                .substring(finalFile.name.lastIndexOf("."))
                .toLowerCase();
              if (allowedUploadTypes.includes(finalSuffix)) {
                // 检查是否超过最大文件数量限制
                if (fileList.length + files.length < 3) {
                  files.push(finalFile);
                } else {
                  message.warning("最多只能上传 3 个文件");
                }
              } else {
                // 记录不符合要求的文件
                invalidFiles.push(finalFile);
              }
            }
          }
        }

        // 如果检测到任何文件，都需要阻止默认粘贴行为（防止文件名被插入到输入框）
        if (hasAnyFile) {
          e.preventDefault();
          e.stopPropagation();

          // 如果有不符合要求的文件，显示错误提示
          if (invalidFiles.length > 0) {
            message.warning(
              `仅支持上传${allowedUploadTypes.join(",")}格式的文件`,
            );
          }

          // 如果有符合要求的文件，进行上传
          if (files.length > 0) {
            fileListRef.current?.uploadFiles(files);
          }
        }
        // 如果没有文件，让默认的文本粘贴行为正常进行
      },
      [fileList.length],
    );

    return (
      <div className="input-wrapper" ref={innerRef}>
        <div className="input-container">
          <div className="input-top">
            <div className="input-field">
              <ShowChatFileList fileList={fileList} onRemove={removeImage} />
              <TextArea
                autoSize={{ minRows: 2, maxRows: 5 }}
                className="message-input"
                placeholder={
                  placeholder || "请输入您的问题，支持多轮对话、图文理解等"
                }
                value={value}
                onChange={(e) => handleInputChange(e.target.value)}
                onPaste={handlePaste}
                onKeyUp={(e) => {
                  if (e.key === "Enter" && !e.shiftKey && !isUploading) {
                    e.preventDefault();
                    handleSend();
                    setNewMessage(false);
                  }
                }}
              />

              <div className="input-bottom-actions">
                <div className="input-bottom-actions-left">
                  {isChatContent && (
                    <div
                      className="input-bottom-actions-left-item"
                      onClick={() => {
                        setThink(false);
                        clearMultiData();
                        clearPendingMessage();
                        openNewChat?.();
                        setNewMessage(true);
                      }}
                    >
                      <AddIcon />
                      新增对话
                    </div>
                  )}
                  <ChatSelector
                    chatConfig={chatConfig ?? {}}
                    onChange={onKnowledgeBaseChange}
                  />
                  {/* <ModelSelector sessionId={sessionId} disabled={isStreaming} /> */}
                  <div
                    className={`input-bottom-actions-left-item ${showHistoryList ? "selected" : ""}`}
                    onClick={openHistory}
                  >
                    对话历史
                  </div>
                  <div
                    className={"input-bottom-actions-left-item"}
                    onClick={() => promptRef.current?.onOpen()}
                  >
                    提示词模板
                  </div>
                </div>

                <div className="input-bottom-actions-right">
                  <Tooltip title="批量对话">
                    <Button
                      type="text"
                      icon={<BatchChatIcon />}
                      onClick={() => batchChatRef.current?.onOpen()}
                    />
                  </Tooltip>
                  <div className="input-bottom-actions-right-item">
                    <ImageUpload
                      updateFiles={updateImageList}
                      listNum={fileList.length}
                      ref={fileListRef}
                      types={allowedUploadTypes}
                      max={3}
                      onBeforeAddFiles={onBeforeAddFiles}
                      icon={<Button icon={<AttachmentIcon />} type="text" />}
                    />
                  </div>
                  <div className="input-bottom-actions-right-item">
                    <SendButton
                      disabled={!value?.length || isUploading}
                      onClick={handleSend}
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <PromptModal
          ref={promptRef}
          onSelectPrompt={(prompt) => onChange(text + " " + prompt)}
        />
        <BatchChatComponent
          ref={batchChatRef}
          cancelFn={(bool) => {
            console.log(bool, "是否展示小红点");
          }}
        />
      </div>
    );
  },
);

ChatInput.displayName = "ChatInput";

export default ChatInput;

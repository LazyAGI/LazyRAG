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
import { useTranslation } from "react-i18next";

const { TextArea } = Input;

const MAX_UPLOAD_FILES = 3;

function getSuffix(f: { name: string }) {
  return f.name.substring(f.name.lastIndexOf(".")).toLowerCase();
}
function isImage(f: { name: string }) {
  return allowedImageTypes.includes(getSuffix(f));
}
function isDoc(f: { name: string }) {
  return allowedFileTypes.includes(getSuffix(f));
}


function preprocessUpload(
  newFiles: File[],
  currentFiles: { name: string }[],
  hasKB: boolean,
  t: (key: string) => string,
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
    toasts.push(t("chat.docImageExclusive"));
    if (hasKB) {
      toasts.push(t("chat.priorityFile"));
    }
  } else if (hasDoc && newImages.length > 0) {
    clearFirst = false;
    filesToAdd = [];
    toasts.push(t("chat.docImageExclusive"));
    if (hasKB) {
      toasts.push(t("chat.priorityFile"));
    }
  } else if (hasImage && newDocs.length > 0) {
    clearFirst = false;
    filesToAdd = [];
    toasts.push(t("chat.docImageExclusive"));
    if (hasKB) {
      toasts.push(t("chat.priorityFile"));
    }
  } else {
    clearFirst = false;
    filesToAdd = newFiles;
    if (hasKB && newFiles.length > 0) {
      toasts.push(t("chat.priorityFile"));
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
  sessionId?: string;
  isStreaming?: boolean;
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
    const { t } = useTranslation();
    const [text, setText] = useState("");
    const previousSessionIdRef = useRef<string | undefined>(undefined);
    const hasSentMessageRef = useRef(false);

    const [fileList, setFileList] = useState<ChatFileList[]>([]);
    const { setPendingMessage, clearPendingMessage } = useChatMessageStore();
    const { saveInputContent, getInputContent, clearInputContent } =
      useChatInputStore();

    const debouncedSaveInput = useMemo(
      () =>
        debounce((conversationId: string, content: string) => {
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
      setTimeout(() => onHeightChange?.(), 0);
    }, [onHeightChange]);

    useImperativeHandle(
      ref,
      () => ({
        clearFiles: () => {
          clearMultiData();
          clearPendingMessage();
        },
        element: innerRef.current,
        uploadFiles: (files: File[]) => {
          fileListRef.current?.uploadFiles(files);
        },
      }),
      [clearPendingMessage, clearMultiData],
    );

    useEffect(() => {
      if (
        sessionId !== undefined &&
        sessionId !== previousSessionIdRef.current
      ) {
        const previousId = previousSessionIdRef.current;

        debouncedSaveInput.cancel();

        if (previousId !== undefined) {
          const previousValue = value || "";
          if (!previousValue || previousValue.trim() === "") {
            clearInputContent(previousId);
          } else {
            saveInputContent(previousId, previousValue);
          }

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

    useEffect(() => {
      return () => {
        debouncedSaveInput.cancel();

        if (hasSentMessageRef.current) {
          hasSentMessageRef.current = false;
          return;
        }

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

    useEffect(() => {
      const checkUploadStatus = () => {
        const uploadingCount = fileListRef.current?.getUploadingCount() || 0;
        setIsUploading(uploadingCount > 0);
      };

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
      setTimeout(() => onHeightChange?.(), 0);
    };

    const removeImage = (uid: string) => {
      fileListRef.current?.removeFile(uid);
      const list = [...fileList].filter((item) => item.uid !== uid);
      setFileList(list);
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

      const hadNoKB = (chatConfig?.knowledgeBaseId?.length ?? 0) === 0;
      const nowHasKB = knowledgeBaseId.length > 0;
      const hasFiles = fileList.length > 0;
      if (hadNoKB && nowHasKB && hasFiles) {
        message.info(t("chat.priorityFile"));
      }
    };

    const hasKB = (chatConfig?.knowledgeBaseId?.length ?? 0) > 0;
    const onBeforeAddFiles = useCallback(
      (newFiles: File[], currentFiles: { name: string }[]) =>
        preprocessUpload(newFiles, currentFiles, hasKB, t),
      [hasKB, t],
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
        setPendingMessage(sendParams);
        setIsChatContent?.(true);
      } else {
        onSend?.(sendParams);
        clearMultiData();
      }

      hasSentMessageRef.current = true;

      if (sessionId !== undefined) {
        debouncedSaveInput.cancel();
        clearInputContent(sessionId);
      }
      onChange("");
      setText("");
    };

    const handleInputChange = (text: string) => {
      onChange(text);
      setText(text);
      if (sessionId !== undefined) {
        debouncedSaveInput(sessionId, text);
      }
    };

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

        for (let i = 0; i < items.length; i++) {
          const item = items[i];

          if (item.kind === "file") {
            hasAnyFile = true;
            const file = item.getAsFile();
            if (file) {
              const fileName = file.name || `pasted-file-${Date.now()}`;
              const suffix = fileName.includes(".")
                ? fileName.substring(fileName.lastIndexOf(".")).toLowerCase()
                : "";

              let finalFile = file;
              if (!suffix && file.type.startsWith("image/")) {
                const ext = file.type.split("/")[1] || "png";
                const newFileName = `pasted-image-${Date.now()}.${ext}`;
                finalFile = new File([file], newFileName, { type: file.type });
              }

              const finalSuffix = finalFile.name
                .substring(finalFile.name.lastIndexOf("."))
                .toLowerCase();
              if (allowedUploadTypes.includes(finalSuffix)) {
                if (fileList.length + files.length < MAX_UPLOAD_FILES) {
                  files.push(finalFile);
                } else {
                  message.warning(t("chat.maxFilesWarning"));
                }
              } else {
                invalidFiles.push(finalFile);
              }
            }
          }
        }

        if (hasAnyFile) {
          e.preventDefault();
          e.stopPropagation();

          if (invalidFiles.length > 0) {
            message.warning(
              t("chat.unsupportedFileType", { types: allowedUploadTypes.join(",") }),
            );
          }

          if (files.length > 0) {
            fileListRef.current?.uploadFiles(files);
          }
        }
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
                  placeholder || t("chat.inputPlaceholder")
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
                      {t("chat.newChat")}
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
                    {t("chat.chatHistory")}
                  </div>
                  <div
                    className={"input-bottom-actions-left-item"}
                    onClick={() => promptRef.current?.onOpen()}
                  >
                    {t("chat.promptTemplate")}
                  </div>
                </div>

                <div className="input-bottom-actions-right">
                  {}
                  <div className="input-bottom-actions-right-item">
                    <ImageUpload
                      updateFiles={updateImageList}
                      listNum={fileList.length}
                      ref={fileListRef}
                      types={allowedUploadTypes}
                      max={MAX_UPLOAD_FILES}
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

          }}
        />
      </div>
    );
  },
);

ChatInput.displayName = "ChatInput";

export default ChatInput;

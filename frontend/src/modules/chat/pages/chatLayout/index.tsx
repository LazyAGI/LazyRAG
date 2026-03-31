import { FC, useRef, useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { message } from "antd";
import { AgentAppsAuth } from "@/components/auth";
import {
  ChatConversationsRequestActionEnum,
  ChatConversationsResponseFinishReasonEnum,
  ChatHistory as BaseChatHistory,
  Conversation,
  Query,
} from "@/api/generated/chatbot-client";

type ChatHistory = BaseChatHistory;

import ChatContainerComponent, {
  ChatImperativeProps,
  ChatMessage,
} from "@/modules/chat/components/newChatContainer";
import "./index.scss";
import { RoleTypes } from "@/modules/chat/constants/common";
import RecordList from "@/modules/chat/components/RecordList";
import UIUtils from "@/modules/chat/utils/ui";
import InitialCard from "@/modules/chat/components/InitialCard";
import { ChatConfig } from "@/modules/chat/components/ChatConfigs";
import { Method, SSE } from "@/modules/chat/utils/sse";
import {
  CHAT_RESUME_STREAM_URL,
  CHAT_STREAM_URL,
  ChatServiceApi,
} from "@/modules/chat/utils/request";
import { CloseOutlined } from "@ant-design/icons";
import { useChatMessageStore } from "@/modules/chat/store/chatMessage";
import {
  useModelSelectionStore,
  MODEL_API_LABELS,
  parseModelSelectionFromModels,
} from "@/modules/chat/store/modelSelection";
import { allowedUploadTypes } from "@/modules/chat/components/ImageUpload";
import { CHAT_RESUME_CONVERSATION_KEY } from "@/modules/chat/constants/chat";
interface IChatLayoutProps {
  setIsChatContent: (isChatContent: boolean) => void;
  initchatConfig: ChatConfig;
  setChatConfigFn: (val: ChatConfig) => void;
}

const ChatLayout: FC<IChatLayoutProps> = (props) => {
  const { t } = useTranslation();
  const { setIsChatContent, initchatConfig, setChatConfigFn } = props;
  const [sessionId, setSessionId] = useState("");
  const [chatConfig, setChatConfig] = useState<ChatConfig>(
    initchatConfig || {},
  );

  const { pendingMessage, clearPendingMessage } = useChatMessageStore();
  const { getModelSelection, setModelSelection } = useModelSelectionStore();
  const [showHistoryList, setShowHistoryList] = useState(true);

  const chatRef = useRef<ChatImperativeProps>(null);

  const [isDragging, setIsDragging] = useState(false);
  const dragCounterRef = useRef(0);

  useEffect(() => {
    setChatConfigFn(initchatConfig);
    setChatConfig(initchatConfig);
  }, [initchatConfig]);

  useEffect(() => {
    if (pendingMessage) {
      const timer = setTimeout(() => {
        chatRef.current?.sendMessage(pendingMessage);
        clearPendingMessage();
      }, 100);

      return () => clearTimeout(timer);
    }
    return undefined;
  }, [pendingMessage, clearPendingMessage]);

  useEffect(() => {
    const conversationId = sessionStorage.getItem(CHAT_RESUME_CONVERSATION_KEY);
    if (!conversationId) {
      return;
    }
    const resolveConversationId = (id: string): Promise<string> => {
      if (!id || !id.startsWith("temp_")) {
        return Promise.resolve(id);
      }
      return ChatServiceApi()
        .conversationServiceListConversations({ pageToken: "", pageSize: 5 })
        .then((listRes) => {
          const conversations = listRes?.data?.conversations ?? [];
          const latest = conversations[0];
          return latest?.conversation_id ?? id;
        })
        .catch(() => id);
    };

    resolveConversationId(conversationId)
      .then((resolvedId) => {
        if (resolvedId !== conversationId) {
          sessionStorage.setItem(CHAT_RESUME_CONVERSATION_KEY, resolvedId);
        }
        return ChatServiceApi()
          .conversationServiceGetChatStatus({ conversationId: resolvedId })
          .then((res) => ({
            resolvedId,
            isGenerating: !!res.data?.is_generating,
          }));
      })
      .catch(() => ({ resolvedId: conversationId, isGenerating: false }))
      .then(({ resolvedId, isGenerating }) => {
        setIsChatContent(true);
        return ChatServiceApi()
          .conversationServiceGetConversationDetail({
            conversation: resolvedId,
          })
          .then((detailRes) => ({ detailRes, resolvedId, isGenerating }));
      })
      .then(({ detailRes, resolvedId, isGenerating }) => {
        const conversation = detailRes.data.conversation;
        const history = detailRes.data.history;
        const tempData = {
          knowledgeBaseId: conversation?.search_config?.dataset_list
            ?.map((d: any) => d.id)
            .filter((id: string) => !!id),
          creators: conversation?.search_config?.creators,
          tags: conversation?.search_config?.tags,
          databaseBaseId: conversation?.search_config?.database_ids?.[0],
        };
        setChatConfig(tempData);
        setChatConfigFn(tempData);
        setSessionId(resolvedId);

        const modelSelection = parseModelSelectionFromModels(
          (conversation as any)?.models,
        );
        setModelSelection(resolvedId, modelSelection);

        const list: ChatMessage[] = [];
        if (history?.length) {
          const lastHistory = history[history.length - 1];
          history.forEach((record: ChatHistory) => {
            list.push({
              role: RoleTypes.USER,
              delta: record.query,
              images: record.input
                ?.filter((i: any) => i.input_type === "image")
                .map((img: any) => ({
                  base64: img?.input_base64,
                  uid: img.file_id,
                })),
              files: record.input
                ?.filter((i: any) => i.input_type === "file")
                .map((f: any) => ({
                  name: f?.uri?.split("/").pop(),
                  uid: f.file_id,
                })),
              finish_reason:
                ChatConversationsResponseFinishReasonEnum.FinishReasonStop,
              inputs: record.input,
              create_time: record.create_time || "",
            });
            const isLastRecord = record === lastHistory;
            const isActuallyGenerating =
              isLastRecord && (!record.result || record.result === "");
            const assistantMsg: any = {
              role: RoleTypes.ASSISTANT,
              reasoning_content: record.reasoning_content,
              delta: record.result || "",
              finish_reason: isActuallyGenerating
                ? ChatConversationsResponseFinishReasonEnum.FinishReasonUnspecified
                : ChatConversationsResponseFinishReasonEnum.FinishReasonStop,
              history_id: record.id,
              sources: record.sources,
              feed_back: record.feed_back,
            };
            if (record.second_result && record.second_id) {
              assistantMsg.answers = [
                {
                  content: record.result || "",
                  index: 0,
                  history_id: record.id,
                  reasoning_content: record.reasoning_content || "",
                  sources: record.sources,
                },
                {
                  content: record.second_result,
                  index: 1,
                  history_id: record.second_id,
                  reasoning_content: record.second_reasoning_content || "",
                },
              ];
              assistantMsg.reasoning_content = "";
              assistantMsg.delta = "";
            }
            list.push(assistantMsg);
          });

          const lastAssistant = list[list.length - 1];
          if (
            isGenerating &&
            lastAssistant?.finish_reason ===
              ChatConversationsResponseFinishReasonEnum.FinishReasonStop
          ) {
            list.push({
              role: RoleTypes.USER,
              delta: "",
              finish_reason:
                ChatConversationsResponseFinishReasonEnum.FinishReasonStop,
              inputs: [],
              is_resumed: true,
            });
            list.push({
              role: RoleTypes.ASSISTANT,
              delta: "",
              reasoning_content: "",
              finish_reason:
                ChatConversationsResponseFinishReasonEnum.FinishReasonUnspecified,
              answers: [],
              sources: [],
            });
          }
        } else if (isGenerating) {
          list.push({
            role: RoleTypes.USER,
            delta: "",
            finish_reason:
              ChatConversationsResponseFinishReasonEnum.FinishReasonStop,
            inputs: [],
            is_resumed: true,
          });
          list.push({
            role: RoleTypes.ASSISTANT,
            delta: "",
            reasoning_content: "",
            finish_reason:
              ChatConversationsResponseFinishReasonEnum.FinishReasonUnspecified,
            answers: [],
            sources: [],
          });
        }
        chatRef.current?.replaceMessageList(resolvedId, list);
        if (isGenerating) {
          chatRef.current?.openResumeSSE?.(resolvedId);
        } else {
          sessionStorage.removeItem(CHAT_RESUME_CONVERSATION_KEY);
        }
      })
      .catch(() => {
        sessionStorage.removeItem(CHAT_RESUME_CONVERSATION_KEY);
      });
  }, []);

  function onOpenSSE(
    input: Query[],
    action: ChatConversationsRequestActionEnum,
    callbacks: Record<string, (e: CustomEvent) => void>,
  ) {
    const modelSelection = getModelSelection(sessionId);

    const hasUploadedFiles = input?.some(
      (q: Query) => q.input_type === "image" || q.input_type === "file",
    );
    const useKnowledgeBase =
      modelSelection === "value_engineering" || modelSelection === "both";
    const datasetList =
      hasUploadedFiles || !useKnowledgeBase
        ? []
        : chatConfig?.knowledgeBaseId?.length
          ? chatConfig.knowledgeBaseId.map((k) => ({ id: k }))
          : [];

    return new SSE(CHAT_STREAM_URL, {
      method: Method.POST,
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        ...AgentAppsAuth.getAuthHeaders(),
      },
      timeout: 300000,
      payload: JSON.stringify({
        action,
        conversation_id: sessionId,
        conversation: {
          search_config: {
            dataset_list: datasetList,
            database_ids: [chatConfig?.databaseBaseId]?.filter((id) => !!id),
            creators: chatConfig?.creators,
            tags: chatConfig?.tags,
          },
        },
        models:
          modelSelection === "both"
            ? [MODEL_API_LABELS.lazyRag, MODEL_API_LABELS.deepSeek]
            : modelSelection === "value_engineering"
              ? [MODEL_API_LABELS.lazyRag]
              : [MODEL_API_LABELS.deepSeek],
        // enable_thinking: think ? true : false,
        stream: true,
        input,
        create_time: new Date().toISOString(),
      }),
      callbacks,
    });
  }

  function onOpenResumeSSE(
    conversationId: string,
    callbacks: Record<string, (e: CustomEvent) => void>,
  ) {
    return new SSE(CHAT_RESUME_STREAM_URL, {
      method: Method.POST,
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        ...AgentAppsAuth.getAuthHeaders(),
      },
      timeout: 300000,
      payload: JSON.stringify({ conversation_id: conversationId }),
      callbacks,
    });
  }

  function setConversationId(id: string) {
    if (id === sessionId) {
      return;
    }
    setSessionId(id);
  }

  function onRecordSelected(data: Conversation) {
    ChatServiceApi()
      .conversationServiceGetConversationDetail({
        conversation: data.conversation_id || "",
      })
      .then((res) => {
        const conversation = res.data.conversation;
        const tempData = {
          knowledgeBaseId: conversation?.search_config?.dataset_list
            ?.map((dataset) => dataset.id)
            .filter((id) => !!id),
          creators: conversation?.search_config?.creators,
          tags: conversation?.search_config?.tags,
          databaseBaseId: conversation?.search_config?.database_ids?.[0],
        };
        setChatConfig(tempData);
        setChatConfigFn(tempData);

        const modelSelection = parseModelSelectionFromModels(
          (conversation as any)?.models,
        );
        if (conversation?.conversation_id) {
          setModelSelection(conversation.conversation_id, modelSelection);
        }

        // Reset messages.
        const history = res.data.history;
        const list: ChatMessage[] = [];
        if (history && history.length > 0) {
          history.forEach((record: ChatHistory) => {
            // Push user.
            list.push({
              role: RoleTypes.USER,
              delta: record.query,
              images: record.input
                ?.filter((input) => {
                  return input.input_type === "image";
                })
                .map((image) => {
                  return {
                    base64: image?.input_base64,
                    uid: image.file_id,
                  };
                }),
              files: record.input
                ?.filter((input) => {
                  return input.input_type === "file";
                })
                .map((file) => {
                  return {
                    name: file?.uri?.split("/").pop(),
                    uid: file.file_id,
                  };
                }),
              finish_reason:
                ChatConversationsResponseFinishReasonEnum.FinishReasonStop,
              inputs: record.input,
              create_time: record.create_time || "xxx-xxx-xxx",
            });

            // Push assistant.
            const assistantMessage: any = {
              role: RoleTypes.ASSISTANT,
              reasoning_content: record.reasoning_content,
              delta: record.result,
              finish_reason:
                ChatConversationsResponseFinishReasonEnum.FinishReasonStop,
              history_id: record.id,
              sources: record.sources,
              feed_back: record.feed_back,
              thinking_time_s: record.thinking_time_s,
            };

            if (record.second_result && record.second_id) {
              assistantMessage.answers = [
                {
                  content: record.result || "",
                  index: 0,
                  history_id: record.id,
                  reasoning_content: record.reasoning_content || "",
                  sources: record.sources,
                  thinking_duration_s: record.thinking_time_s,
                },
                {
                  content: record.second_result,
                  index: 1,
                  history_id: record.second_id,
                  reasoning_content: record.second_reasoning_content || "",
                  sources: record.sources,
                  thinking_duration_s: record.second_thinking_time_s,
                },
              ];

              assistantMessage.reasoning_content = "";
              assistantMessage.delta = "";
            }

            list.push(assistantMessage);
          });
        }
        chatRef.current?.replaceMessageList(
          conversation?.conversation_id || "",
          list,
        );
      });
  }

  function deleteHistory(data: Conversation) {
    if (data.conversation_id === sessionId) {
      chatRef.current?.createNewChat();
    }
  }

  function parseErrorData(data: string) {
    const dataObject = UIUtils.jsonParser(data) || {};
    return dataObject.message;
  }

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

    (chatRef.current as any)?.uploadFiles?.(files);
  };

  return (
    <div
      className="detail-container"
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
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
      <ChatContainerComponent
        ref={chatRef}
        initialCard={<InitialCard />}
        sessionId={sessionId}
        onOpenSSE={onOpenSSE}
        onOpenResumeSSE={onOpenResumeSSE}
        onConversationIdChange={setConversationId}
        parseErrorData={parseErrorData}
        setShowHistoryList={() => setShowHistoryList(!showHistoryList)}
        showHistoryList={showHistoryList}
        setIsChatContent={setIsChatContent}
        chatConfig={chatConfig}
        setChatConfig={setChatConfig}
        setChatConfigFn={setChatConfigFn}
      />
      {showHistoryList && (
        <div className="right-box">
          <CloseOutlined
            style={{
              position: "absolute",
              top: 12,
              right: 12,
              fontSize: 20,
              cursor: "pointer",
              opacity: 0.45,
            }}
            onClick={() => {
              setShowHistoryList(false);
            }}
          />
          <RecordList
            currentSessionId={sessionId}
            onSelected={onRecordSelected}
            onRemove={deleteHistory}
          />
        </div>
      )}
    </div>
  );
};

export default ChatLayout;

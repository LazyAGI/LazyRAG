import { FC, useRef, useState, useEffect } from "react";
import { message } from "antd";
import { AgentAppsAuth } from "@/components/auth";
import {
  ChatConversationsRequestActionEnum,
  ChatConversationsResponseFinishReasonEnum,
  ChatHistory as BaseChatHistory,
  Conversation,
  Query,
} from "@/api/generated/chatbot-client";

// 直接使用 openapi 的 ChatHistory 类型，已包含所有需要的字段
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
  MODEL_OPTIONS,
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
  const { setIsChatContent, initchatConfig, setChatConfigFn } = props;
  const [sessionId, setSessionId] = useState("");
  const [chatConfig, setChatConfig] = useState<ChatConfig>(
    initchatConfig || {},
  );

  const { pendingMessage, clearPendingMessage } = useChatMessageStore();
  const { getModelSelection, setModelSelection } = useModelSelectionStore();
  const [showHistoryList, setShowHistoryList] = useState(true);

  const chatRef = useRef<ChatImperativeProps>(null);

  // 拖拽相关状态
  const [isDragging, setIsDragging] = useState(false);
  const dragCounterRef = useRef(0);

  useEffect(() => {
    setChatConfigFn(initchatConfig);
    setChatConfig(initchatConfig);
  }, [initchatConfig]);

  // 在组件首次加载时检查是否有待发送的消息
  useEffect(() => {
    if (pendingMessage) {
      // 等待组件完全渲染后再发送消息
      const timer = setTimeout(() => {
        chatRef.current?.sendMessage(pendingMessage);
        clearPendingMessage();
      }, 100);

      return () => clearTimeout(timer);
    }
    return undefined;
  }, [pendingMessage, clearPendingMessage]);

  // 刷新后续传：有保存的会话 id 时恢复当前对话页（无论是否正在生成）
  useEffect(() => {
    const conversationId = sessionStorage.getItem(CHAT_RESUME_CONVERSATION_KEY);
    if (!conversationId) {
      return;
    }
    // 临时 id（未收到 SSE 返回的真实 id）无法用于 getChatStatus，先尝试拉取会话列表以解析真实 id
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
        // 无论是否正在生成，都加载会话详情并停留在当前对话页
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

        // 从后端 conversation.models 解析并设置模型选择
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
            // 只有当是最后一条记录且 result 为空或部分时，才标记为正在生成中
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

    // 若本次请求带有上传文件（图片/文档），忽略知识库选择；不修改用户已选/置顶的知识库
    const hasUploadedFiles = input?.some(
      (q: Query) => q.input_type === "image" || q.input_type === "file",
    );
    // DeepSeek 不接入知识库；LazyRAG 根据用户是否选择知识库确定
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
        // 使用 models 指定模型：双模比较传两个，单模型传一个（LazyRAG 大模型 / DeepSeek）
        models:
          modelSelection === "both"
            ? [MODEL_OPTIONS[0].label, MODEL_OPTIONS[1].label] // ["LazyRAG 大模型", "DeepSeek"]
            : modelSelection === "value_engineering"
              ? [MODEL_OPTIONS[0].label]
              : [MODEL_OPTIONS[1].label],
        // 是否开启思考模式
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
    // 允许设置为空字符串（新对话）
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

        // 从后端 conversation.models 解析并设置模型选择
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

            // 根据 second_result、second_id 判断是否展示双回复
            // 只需要 second_result 和 second_id 存在即可，second_reasoning_content 可以为空
            if (record.second_result && record.second_id) {
              // 有双回复数据，构造 answers 数组
              assistantMessage.answers = [
                {
                  content: record.result || "",
                  index: 0,
                  history_id: record.id,
                  reasoning_content: record.reasoning_content || "",
                  sources: record.sources,
                  thinking_duration_s: record.thinking_time_s, // 第一个回答的思考时间
                },
                {
                  content: record.second_result,
                  index: 1,
                  history_id: record.second_id,
                  reasoning_content: record.second_reasoning_content || "",
                  sources: record.sources, // 如果第二个回复有独立的 sources，需要从 record.second_sources 获取
                  thinking_duration_s: record.second_thinking_time_s, // 第二个回答的思考时间
                },
              ];

              // 清除顶层的 reasoning_content 和 delta，避免重复显示
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

    // 调用 ChatContainerComponent 的 uploadFiles 方法
    // 通过 ref 访问 ChatContainerComponent 内部的 chatInputRef
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

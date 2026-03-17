import { FC, useRef, useState } from "react";
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
} from "@/modules/chat/components/ChatContainer";
import "./index.scss";
import { RoleTypes } from "@/modules/chat/constants/common";
import RecordList, {
  RecordListImperativeProps,
} from "@/modules/chat/components/RecordList";
import UIUtils from "@/modules/chat/utils/ui";
import InitialCard from "@/modules/chat/components/InitialCard";
import ChatConfigs, { ChatConfig } from "@/modules/chat/components/ChatConfigs";
import { Method, SSE } from "@/modules/chat/utils/sse";
import { CHAT_STREAM_URL, ChatServiceApi } from "@/modules/chat/utils/request";
import { useEffect } from "react";
import { useConversationSettings } from "@/modules/chat/store/conversationSettings";

const ChatPage: FC = () => {
  const [sessionId, setSessionId] = useState("");
  const [chatConfig, setChatConfig] = useState<ChatConfig>();
  const { enableMultipleAnswers, fetchSwitchStatus } =
    useConversationSettings();

  const chatRef = useRef<ChatImperativeProps>(null);
  const recordListRef = useRef<RecordListImperativeProps>(null);
  const previousSessionIdRef = useRef<string>("");

  // 进入 chat 界面时获取双回复开关状态
  useEffect(() => {
    fetchSwitchStatus();
  }, [fetchSwitchStatus]);

  function onOpenSSE(
    input: Query[],
    action: ChatConversationsRequestActionEnum,
    callbacks: Record<string, (e: CustomEvent) => void>,
  ) {
    // 若本次请求带有上传文件（图片/文档），忽略知识库选择；不修改用户已选/置顶的知识库
    const hasUploadedFiles = input?.some(
      (q: Query) => q.input_type === "image" || q.input_type === "file",
    );
    const datasetList = hasUploadedFiles
      ? []
      : chatConfig?.knowledgeBaseId?.map((id) => ({ id })) || [];

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
        // 使用 models 指定模型：双答时传 LazyRAG 大模型和 DeepSeek，单答时传 LazyRAG 大模型
        models: enableMultipleAnswers
          ? ["LazyRAG 大模型", "DeepSeek"]
          : ["LazyRAG 大模型"],
        stream: true,
        input,
      }),
      callbacks,
    });
  }

  function setConversationId(id: string) {
    if (id === sessionId) {
      return;
    }
    setSessionId(id);
  }

  // 监听 sessionId 变化，当新增对话（从非空变为空字符串）时刷新会话历史
  useEffect(() => {
    // 只在从非空变为空时刷新，避免首次加载时触发
    if (
      sessionId === "" &&
      previousSessionIdRef.current !== "" &&
      recordListRef.current
    ) {
      recordListRef.current.refresh();
    }
    previousSessionIdRef.current = sessionId;
  }, [sessionId]);

  function onRecordSelected(data: Conversation) {
    ChatServiceApi()
      .conversationServiceGetConversationDetail({
        conversation: data.conversation_id || "",
      })
      .then((res) => {
        // Reset configs.
        const conversation = res.data.conversation;
        setChatConfig({
          knowledgeBaseId: conversation?.search_config?.dataset_list
            .map((dataset) => dataset.id)
            .filter((id) => !!id),
          creators: conversation?.search_config?.creators,
          tags: conversation?.search_config?.tags,
          databaseBaseId: conversation?.search_config?.database_ids?.[0],
        });

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
            if (
              enableMultipleAnswers &&
              record.second_result &&
              record.second_id
            ) {
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

  function onChatConfigChanged(config: ChatConfig) {
    setChatConfig((prev) => {
      const updated: ChatConfig = { ...prev };

      (Object.keys(config) as Array<keyof ChatConfig>).forEach((key) => {
        updated[key] = config[key] as any;
      });
      return updated;
    });
  }

  // 生成新的对话ID（使用浏览器原生API，无需外部依赖）
  function generateNewConversationId(): string {
    // 使用浏览器原生的 crypto.randomUUID()，兼容性良好（Chrome 92+, Firefox 95+, Safari 15.4+）
    if (typeof crypto !== "undefined" && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    // 降级方案：使用时间戳 + 随机数生成唯一ID
    return `conv_${Date.now()}_${Math.random().toString(36).substring(2, 15)}`;
  }

  function handleCreateNewChat() {
    // 生成新的UUID作为conversation_id
    const newConversationId = generateNewConversationId();
    // 先通知ChatContainer创建新对话（传入新的ID）
    chatRef.current?.replaceMessageList(newConversationId, []);
    // 更新会话ID状态
    setSessionId(newConversationId);
    // 注意：不在这里刷新会话历史，只在收到服务器返回的conversation_id时刷新（通过onNewConversationCreated）
  }

  function handleNewConversationCreated(_conversationId: string) {
    // 当收到新会话的conversation_id时，刷新会话历史
    if (recordListRef.current) {
      recordListRef.current.refresh();
    }
  }

  return (
    <div className="detail-container">
      <div className="left-box">
        <div className="title">配置</div>
        <ChatConfigs
          configs={chatConfig || {}}
          onChange={onChatConfigChanged}
        />
        <RecordList
          ref={recordListRef}
          currentSessionId={sessionId}
          onSelected={onRecordSelected}
          onRemove={deleteHistory}
        />
      </div>
      <ChatContainerComponent
        ref={chatRef}
        initialCard={<InitialCard />}
        onOpenSSE={onOpenSSE}
        onConversationIdChange={setConversationId}
        parseErrorData={parseErrorData}
        onCreateNewChat={handleCreateNewChat}
        onNewConversationCreated={handleNewConversationCreated}
      />
    </div>
  );
};

export default ChatPage;

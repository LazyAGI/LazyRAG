import {
  useRef,
  useState,
  useEffect,
  forwardRef,
  useImperativeHandle,
  useCallback,
  ReactElement,
} from "react";
import { Spin, Flex, message } from "antd";
import {
  DoubleRightOutlined,
  DownOutlined,
  UpOutlined,
} from "@ant-design/icons";
import {
  ChatConversationsRequestActionEnum,
  ChatConversationsResponseFinishReasonEnum,
  Query,
  Source,
} from "@/api/generated/chatbot-client";
import { RcFile } from "antd/es/upload";

import UIUtils from "@/modules/chat/utils/ui";
import { RoleTypes } from "@/modules/chat/constants/common";
import "./index.scss";
import MarkdownViewer from "@/modules/chat/components/MarkdownViewer";
import ChatImages, { ChatImage } from "../ChatImages";
import ChatFiles from "../ChatFiles";
import MessageList from "./components/MessageList";
import ChatInput, {
  ChatFileList,
  SendMessageParams,
  ChatInputImperativeProps,
} from "../ChatInput";
import { ChatConfig } from "../ChatConfigs";
import { allowedImageTypes } from "../ImageUpload";
import { streamManager } from "@/modules/chat/utils/StreamManager";
import { useModelSelectionStore } from "@/modules/chat/store/modelSelection";
import type { PreferenceType } from "../MultiAnswerDisplay";
import { ChatServiceApi } from "@/modules/chat/utils/request";
import { useChatMessageStore } from "@/modules/chat/store/chatMessage";
import { CHAT_RESUME_CONVERSATION_KEY } from "@/modules/chat/constants/chat";

const ThinkIcon = new URL("../../assets/images/think.png", import.meta.url)
  .href;

export interface ChatImperativeProps {
  replaceMessageList: (id: string, data: any[]) => void;
  createNewChat: () => void;
  sendMessage: (params: SendMessageParams) => void;
  uploadFiles?: (files: File[]) => void;
  openResumeSSE?: (conversationId: string) => void;
}

interface Props {
  canChat?: boolean;
  initialCard?: ReactElement | string;
  sessionId?: string; // 当前会话ID，用于模型选择等
  onOpenSSE: (
    input: any[],
    action: ChatConversationsRequestActionEnum,
    callbacks: Record<string, (e: CustomEvent) => void>,
  ) => any; // Return new SSE.
  onOpenResumeSSE?: (
    conversationId: string,
    callbacks: Record<string, (e: CustomEvent) => void>,
  ) => any; // 续传 SSE
  onConversationIdChange?: (conversationId: string) => void;
  parseErrorData: (data: string) => string;
  setShowHistoryList: (show: boolean) => void;
  showHistoryList: boolean;
  setIsChatContent: (isChatContent: boolean) => void;
  chatConfig?: ChatConfig;
  setChatConfig?: (chatConfig: ChatConfig) => void;
  setChatConfigFn: (chatConfig: ChatConfig) => void;
}

export interface ChatMessage {
  role?: string;
  delta?: string;
  images?: {
    base64?: string;
    uid?: string;
  }[];
  files?: {
    name?: string;
    uid?: string;
  }[];
  finish_reason?: string;
  inputs?: Query[];
  reasoning_content?: string;
  history_id?: string;
  sources?: Source[];
  feed_back?: string;
  answers?: Array<{
    content: string;
    index: number;
    history_id?: string;
    reasoning_content?: string;
    sources?: Source[];
    thinking_duration_s?: string;
  }>;
  answer_index?: number;
  create_time?: string;
  is_resumed?: boolean;
}

const ChatContainerComponent = forwardRef<ChatImperativeProps, Props>(
  (props, ref) => {
    const {
      canChat = true,
      initialCard,
      sessionId = "",
      onOpenSSE,
      onOpenResumeSSE,
      onConversationIdChange,
      parseErrorData,
      setShowHistoryList,
      showHistoryList,
      setIsChatContent,
      chatConfig,
      setChatConfig,
      setChatConfigFn,
    } = props;
    const { getModelSelection, setModelSelection, resetForNewChat } =
      useModelSelectionStore();

    const handlePreferenceSelect = useCallback(
      (preference: PreferenceType, sessId?: string) => {
        const sid =
          sessId ?? sessionId ?? currentConversationIdRef.current ?? "";
        if (preference === "prefer_first") {
          setModelSelection(sid, "value_engineering");
          message.success("后续回答将为 LazyRAG 大模型");
        } else if (preference === "prefer_second") {
          setModelSelection(sid, "deepseek");
          message.success("后续回答将为DeepSeek");
        } else if (preference === "similar") {
          message.success("感谢您的反馈，后续回答将仍为双模型");
        } else if (preference === "neither") {
          message.success("抱歉您的体验不佳，反馈已收到，后续回答将仍为双模型");
        }
      },
      [sessionId, setModelSelection],
    );
    const { clearPendingMessage: clearStorePendingMessage } =
      useChatMessageStore();
    const isMouseScrollingRef = useRef(false);
    const sseRef = useRef<any>(null);
    const fileRef = useRef<any>(null);
    const chatContentRef = useRef<HTMLDivElement>(null);
    const currentConversationIdRef = useRef<string>("");
    const messageListRef = useRef<any[]>([]); // 使用ref保存最新的消息列表，避免闭包问题
    const saveTimerRef = useRef<number | null>(null); // 用于节流保存
    // 为每个会话维护独立的消息缓存，避免后台会话累加时使用旧数据
    const conversationMessagesCache = useRef<Map<string, any[]>>(new Map());

    const [messageList, setMessageList] = useState<any[]>([]);
    const [loading, setLoading] = useState(false);
    const [content, setContent] = useState("");
    // 使用 Map 存储每个思考过程的收缩状态，key 为唯一标识符
    const [thinkingCollapseMap, setThinkingCollapseMap] = useState<
      Map<string, boolean>
    >(new Map());
    const [fileList, setFileList] = useState<ChatFileList[]>([]);
    const [showScrollButton, setShowScrollButton] = useState(false);
    const chatInputRef = useRef<ChatInputImperativeProps>(null);
    const [inputHeight, setInputHeight] = useState(120);
    // 表示正在流式输出中
    const [IS_STREAMING, setIS_STREAMING] = useState(false);

    useImperativeHandle(ref, () => ({
      replaceMessageList,
      createNewChat,
      sendMessage,
      uploadFiles: (files: File[]) => {
        chatInputRef.current?.uploadFiles(files);
      },
      openResumeSSE: onOpenResumeSSE ? openResumeSSE : undefined,
    }));

    useEffect(() => {
      return () => {
        // 组件卸载时，清理定时器和当前会话的活跃状态
        if (saveTimerRef.current) {
          clearTimeout(saveTimerRef.current);
          // 在清理前立即保存一次，确保数据不丢失
          const currentId = currentConversationIdRef.current;
          if (currentId && streamManager.hasActiveStream(currentId)) {
            streamManager.saveMessageList(currentId, messageListRef.current);
          }
        }

        // 组件卸载时，清理所有已完成流的资源，但保留进行中的流
        streamManager.cleanupFinishedStreams();

        // 清理所有缓存（因为组件已卸载，不需要保留）
        conversationMessagesCache.current.clear();

        if (currentConversationIdRef.current) {
          streamManager.setActiveConversation(null);
        }
      };
    }, []);

    function getFileUrls(
      files: (RcFile & { uri: string })[] | undefined,
      images?: ChatImage[],
    ) {
      if (!files) {
        return [];
      }

      return files?.map((file) => {
        return {
          uri: file.uri,
          base64: images
            ? images.find((image) => image.uid === file.uid)?.base64
            : "",
        };
      });
    }

    function clearMultiData() {
      setFileList([]);
      fileRef.current?.clear();
    }

    function sendMessage(params: SendMessageParams) {
      const { text, clearInput = true, create_time } = params;
      if (loading || !canChat || !text) {
        return;
      }

      if (params?.fileList) {
        setFileList(params.fileList);
      }
      if (params?.fileListRef) {
        fileRef.current = params.fileListRef.current;
      }

      const tempGroup =
        Object.groupBy(params?.fileList ?? [], (item) => {
          const suffix = item.name
            .substring(item.name.lastIndexOf("."))
            .toLowerCase();
          return allowedImageTypes.includes(suffix) ? "image" : "file";
        }) ?? {};
      const tempFileGroup =
        Object.groupBy(params?.files ?? [], (item) => {
          const suffix = item.name
            .substring(item.name.lastIndexOf("."))
            .toLowerCase();
          return allowedImageTypes.includes(suffix) ? "image" : "file";
        }) ?? {};

      const inputs = [
        { input_type: "text", text },
        ...getFileUrls(tempFileGroup?.image, tempGroup?.image).map((image) => {
          return {
            input_type: "image",
            uri: image.uri || "",
            input_base64: image.base64 || "",
          };
        }),
        ...getFileUrls(tempFileGroup?.file, tempGroup?.file).map((file) => {
          return { input_type: "file", uri: file.uri || "" };
        }),
      ];

      if (clearInput) {
        setContent("");
        clearMultiData();
      }
      // 发送时记录当前模型选择，确保该轮问答的展示模式不随后续切换变化
      const currentModelSelection = getModelSelection(
        currentConversationIdRef.current || sessionId,
      );

      const userMessage = {
        delta: text,
        role: RoleTypes.USER,
        images: tempGroup?.image,
        files: tempGroup?.file,
        fileList,
        inputs,
        finish_reason:
          ChatConversationsResponseFinishReasonEnum.FinishReasonStop,
        create_time,
        model_mode: currentModelSelection,
      };
      // 创建一个全新的空助手消息
      const assistantMessage = {
        role: RoleTypes.ASSISTANT,
        delta: "",
        reasoning_content: "",
        finish_reason:
          ChatConversationsResponseFinishReasonEnum.FinishReasonUnspecified,
        answers: [],
        sources: [],
        model_mode: currentModelSelection,
      };
      const newMessageList = [...messageList, userMessage, assistantMessage];
      messageListRef.current = newMessageList; // 更新ref
      setMessageList(newMessageList);

      isMouseScrollingRef.current = true;
      scrollToEnd();
      openSSE(inputs, ChatConversationsRequestActionEnum.ChatActionNext);

      // 发送消息后，立即保存消息列表（包括用户的问题和空的助手消息）
      const currentId = currentConversationIdRef.current;
      if (currentId) {
        conversationMessagesCache.current.set(currentId, newMessageList);
        streamManager.saveMessageList(currentId, newMessageList);
      }
    }

    const openSSE = (
      input: any[],
      action: ChatConversationsRequestActionEnum,
    ) => {
      setLoading(true);
      setIS_STREAMING(true);

      // 为每个SSE连接分配一个所属会话ID
      let conversationId = currentConversationIdRef.current;
      if (!conversationId) {
        // 生成临时ID用于注册流，等待服务器返回conversation_id后再迁移
        conversationId = `temp_${Date.now()}_${Math.random().toString(36).substring(2, 15)}`;
        currentConversationIdRef.current = conversationId;
      } else {
        // 重新生成场景：已有真实 conversation_id，持久化供刷新后续传
        sessionStorage.setItem(CHAT_RESUME_CONVERSATION_KEY, conversationId);
      }
      const callbacks: Record<string, (e: CustomEvent) => void> = {
        message: (e) => onMessage(e),
        error: (e) => onError(e),
        timeout: (e) => onTimeout(e),
      };

      // 不要在创建SSE时传入callbacks，避免重复注册监听器
      // 只通过streamManager.registerStream注册一次
      const sse = onOpenSSE(input, action, {});
      sseRef.current = sse;

      // 使用流管理器注册流（唯一注册点）
      streamManager.registerStream(conversationId, sse, callbacks);
      streamManager.setActiveConversation(conversationId);

      // 🔧 保存当前的消息列表到streamManager和conversationMessagesCache
      const currentList = messageListRef.current;
      conversationMessagesCache.current.set(conversationId, currentList);
      streamManager.saveMessageList(conversationId, currentList);

      // 新会话（temp_ id）时，从会话列表尽早拿到真实 conversation_id 并持久化，便于「发送后、模型未开始回复前」刷新仍能停留在当前对话页
      if (conversationId.startsWith("temp_")) {
        const tempId = conversationId;
        setTimeout(() => {
          ChatServiceApi()
            .conversationServiceListConversations({
              pageToken: "",
              pageSize: 5,
            })
            .then((res) => {
              const conversations = res?.data?.conversations ?? [];
              const latest = conversations[0];
              const realId = latest?.conversation_id;
              if (!realId) return;
              if (currentConversationIdRef.current !== tempId) return;
              sessionStorage.setItem(CHAT_RESUME_CONVERSATION_KEY, realId);
              onConversationIdChange?.(realId);
            })
            .catch(() => {});
        }, 400);
      }
    };

    function openResumeSSE(conversationId: string) {
      if (!onOpenResumeSSE) {
        return;
      }
      setLoading(true);
      setIS_STREAMING(true);
      currentConversationIdRef.current = conversationId;

      const callbacks: Record<string, (e: CustomEvent) => void> = {
        message: (e) => onMessage(e),
        error: (e) => onError(e),
        timeout: (e) => onTimeout(e),
      };
      // 不要在创建SSE时传入callbacks，避免重复注册监听器（与openSSE保持一致）
      // 只通过streamManager.registerStream注册一次
      const sse = onOpenResumeSSE(conversationId, {});
      sseRef.current = sse;

      streamManager.registerStream(conversationId, sse, callbacks);
      streamManager.setActiveConversation(conversationId);
      const currentList = messageListRef.current;
      conversationMessagesCache.current.set(conversationId, currentList);
      streamManager.saveMessageList(conversationId, currentList);
      sessionStorage.setItem(CHAT_RESUME_CONVERSATION_KEY, conversationId);
    }

    function closeSSE() {
      // 不关闭流，只清理本地引用和loading状态
      // 流由StreamManager统一管理，切换会话时不会中断
      sseRef.current = null;
      setLoading(false);
      setIS_STREAMING(false);
    }

    function onMessage(e: any) {
      const result = UIUtils.jsonParser(e.data)?.result;
      if (!result) {
        return;
      }

      // 固定住当前会话ID，避免在处理过程中被切换
      const messageConversationId = result.conversation_id || "";
      const currentConversationIdAtStart = currentConversationIdRef.current;

      // 判断这个消息是否属于当前活跃会话
      const isUsingTempId = currentConversationIdAtStart.startsWith("temp_");

      let isActiveConversation = false;
      if (messageConversationId) {
        // 如果消息有conversation_id
        if (isUsingTempId) {
          // 当前使用临时ID，检查这个conversation_id是否是新会话的第一条消息
          // 如果这个conversation_id已经在streamManager中存在，说明是旧会话的消息
          const stream = streamManager.getStream(messageConversationId);
          isActiveConversation = !stream;
        } else {
          // 当前有真实ID，直接比较
          isActiveConversation =
            messageConversationId === currentConversationIdAtStart;
        }
      } else {
        // 如果消息没有conversation_id（某些初始化消息），只有当前ID为空时才接受
        isActiveConversation = currentConversationIdAtStart === "";
      }

      // 只在活跃会话第一次收到conversation_id时才更新状态
      const isFirstTimeReceivingId =
        result.conversation_id &&
        result.conversation_id !== currentConversationIdRef.current &&
        isActiveConversation;

      if (isFirstTimeReceivingId) {
        if (onConversationIdChange) {
          onConversationIdChange(result.conversation_id);
        }

        // 刷新后续传：流式输出时持久化 conversation_id
        sessionStorage.setItem(
          CHAT_RESUME_CONVERSATION_KEY,
          result.conversation_id,
        );

        // 更新当前会话ID
        const previousConversationId = currentConversationIdRef.current;
        const isPreviousTempId = previousConversationId.startsWith("temp_");

        // 🔧 迁移模型选择：从空字符串迁移到真实会话ID
        // 新建会话时，模型选择存储在 '' 下，需要迁移到真实会话ID
        // 这样后续问答也能正确获取模型选择
        const newChatModelSelection = getModelSelection("");
        setModelSelection(result.conversation_id, newChatModelSelection);

        if (isPreviousTempId) {
          // 🔧 先保存当前消息列表到临时ID的缓存，确保不丢失
          const currentList = messageListRef.current;
          conversationMessagesCache.current.set(
            previousConversationId,
            currentList,
          );

          // 更新当前会话ID
          currentConversationIdRef.current = result.conversation_id;
          streamManager.setActiveConversation(result.conversation_id);

          // 从临时ID迁移到真实ID
          if (sseRef.current) {
            // 先手动清理临时ID的监听器，但保留SSE连接
            const tempStream = streamManager.getStream(previousConversationId);
            if (tempStream) {
              const tempCallbacks = streamManager.getCallbacks(
                previousConversationId,
              );
              if (tempCallbacks) {
                if (tempCallbacks.message) {
                  tempStream.removeEventListener(
                    "message",
                    tempCallbacks.message,
                  );
                }
                if (tempCallbacks.error) {
                  tempStream.removeEventListener("error", tempCallbacks.error);
                }
                if (tempCallbacks.timeout) {
                  tempStream.removeEventListener(
                    "timeout",
                    tempCallbacks.timeout,
                  );
                }
              }
            }
            // 清理临时ID的状态和注册（但不关闭SSE连接）
            streamManager.clearStreamState(previousConversationId);
            streamManager.removeStreamEntry(previousConversationId);

            // 用真实ID重新注册（使用同一个SSE实例）
            const streamCallbacks: Record<
              string,
              (event: CustomEvent) => void
            > = {
              message: (event) => onMessage(event),
              error: (event) => onError(event),
              timeout: (event) => onTimeout(event),
            };
            streamManager.registerStream(
              result.conversation_id,
              sseRef.current,
              streamCallbacks,
            );

            // 🔧 迁移缓存：将临时ID的缓存迁移到真实ID
            const cachedList = conversationMessagesCache.current.get(
              previousConversationId,
            );
            if (cachedList) {
              conversationMessagesCache.current.set(
                result.conversation_id,
                cachedList,
              );
              conversationMessagesCache.current.delete(previousConversationId);
            }

            streamManager.saveMessageList(result.conversation_id, currentList);
          }
        }
      }

      // 只有活跃会话的完成状态才影响滚动行为
      if (
        isActiveConversation &&
        result.finish_reason ===
          ChatConversationsResponseFinishReasonEnum.FinishReasonStop
      ) {
        isMouseScrollingRef.current = true;
      }

      // 🔧 当流结束时，立即清理该会话的所有数据
      if (
        result.finish_reason !==
        ChatConversationsResponseFinishReasonEnum.FinishReasonUnspecified
      ) {
        // 只有活跃会话结束时才清理本地SSE引用和loading状态
        if (isActiveConversation) {
          setIS_STREAMING(false);
          closeSSE();
        }

        // 🔧 立即清理StreamManager中的流和缓存（不再延迟）
        const cleanupConversationId =
          messageConversationId || currentConversationIdAtStart;
        if (cleanupConversationId) {
          streamManager.closeAndCleanup(cleanupConversationId);
          conversationMessagesCache.current.delete(cleanupConversationId);
        }
        sessionStorage.removeItem(CHAT_RESUME_CONVERSATION_KEY);
      }

      // 定义一个通用的消息列表更新函数
      const updateMessageListInternal = (list: any[]) => {
        const newList = [...list];
        let assistantMessage =
          newList.length > 0 ? newList[newList.length - 1] : null;

        // 检查最后一条助手消息是否已完成
        // 如果已完成，不应该在它上面累加新内容，需要创建新的轮次
        const isLastAssistantCompleted =
          assistantMessage?.role === RoleTypes.ASSISTANT &&
          assistantMessage?.finish_reason ===
            ChatConversationsResponseFinishReasonEnum.FinishReasonStop;

        if (
          !assistantMessage ||
          assistantMessage.role !== RoleTypes.ASSISTANT ||
          isLastAssistantCompleted
        ) {
          // 需要创建新的助手消息
          // 如果最后一条助手消息已完成，说明续传的内容属于新的一轮对话
          // 这种情况下，用户消息可能还没有被添加到列表中
          if (isLastAssistantCompleted) {
            // 添加占位用户消息，标记为恢复的消息
            newList.push({
              role: RoleTypes.USER,
              delta: "",
              finish_reason:
                ChatConversationsResponseFinishReasonEnum.FinishReasonStop,
              inputs: [],
              is_resumed: true,
            });
          }

          assistantMessage = {
            role: RoleTypes.ASSISTANT,
            delta: "",
            reasoning_content: "",
            finish_reason:
              ChatConversationsResponseFinishReasonEnum.FinishReasonUnspecified,
            answers: [],
          };
          newList.push(assistantMessage);
        }

        // 检查是否启用了多回答功能，并且后端返回了 history_id
        // 优先使用消息中保存的 model_mode，避免新会话 ID 变化导致获取不到正确的模型选择
        const convModelSelection =
          assistantMessage?.model_mode ||
          getModelSelection(
            messageConversationId || currentConversationIdAtStart,
          );
        const isMultiAnswerMode =
          convModelSelection === "both" && result.history_id;

        if (isMultiAnswerMode) {
          // 双回复模式：根据 history_id 分流到不同的 answer
          if (!assistantMessage.answers) {
            assistantMessage.answers = [];
          }

          // 根据 history_id 查找对应的 answer
          let targetAnswer = assistantMessage.answers.find(
            (ans: any) => ans.history_id === result.history_id,
          );

          if (!targetAnswer) {
            // 如果是新的 history_id，创建新的 answer
            const answerIndex = assistantMessage.answers.length;
            targetAnswer = {
              content: "",
              index: answerIndex,
              history_id: result.history_id,
              reasoning_content: "",
              sources: [],
            };
            assistantMessage.answers.push(targetAnswer);
          }

          // 累加该回答的内容
          targetAnswer.content += result.delta || "";
          targetAnswer.reasoning_content =
            (targetAnswer.reasoning_content || "") +
            (result.reasoning_content || "");

          // 更新 sources（如果有）
          if (result.sources && result.sources.length > 0) {
            targetAnswer.sources = result.sources;
          }

          // 更新 thinking_duration_s（如果有）
          if (result.thinking_duration_s) {
            targetAnswer.thinking_duration_s = result.thinking_duration_s;
          }

          // 更新整体消息的 finish_reason 和 conversation_id
          assistantMessage = {
            ...assistantMessage,
            finish_reason:
              result.finish_reason || assistantMessage.finish_reason,
            conversation_id:
              result.conversation_id || assistantMessage.conversation_id,
            id: result.messageId || assistantMessage.id,
          };
        } else {
          // 单回答模式：保持原有逻辑
          const previousDelta = assistantMessage.delta || "";
          const previousReasoningContent =
            assistantMessage.reasoning_content || "";

          assistantMessage = {
            ...assistantMessage,
            ...result,
            id: result.messageId,
            delta: previousDelta + (result.delta || ""),
            reasoning_content:
              previousReasoningContent + (result.reasoning_content || ""),
            sources:
              result.sources && result.sources.length > 0
                ? result.sources
                : assistantMessage.sources,
          };
        }

        newList[newList.length - 1] = assistantMessage;
        return newList;
      };

      // 如果是活跃会话，更新UI和保存
      if (isActiveConversation) {
        setMessageList((list) => {
          const newList = updateMessageListInternal(list);

          // 更新ref保存最新的消息列表
          messageListRef.current = newList;

          // 同时更新缓存
          const currentId = currentConversationIdRef.current;
          if (currentId) {
            conversationMessagesCache.current.set(currentId, newList);
          }

          // 使用节流保存消息列表到StreamManager
          if (currentId && streamManager.hasActiveStream(currentId)) {
            if (saveTimerRef.current) {
              clearTimeout(saveTimerRef.current);
            }
            saveTimerRef.current = setTimeout(() => {
              streamManager.saveMessageList(currentId, messageListRef.current);
              saveTimerRef.current = null;
            }, 100);
          }

          return newList;
        });

        if (isMouseScrollingRef.current) {
          scrollToEnd();
        }
      } else {
        // 🔧 后台会话：只更新缓存，不更新UI
        if (messageConversationId) {
          // 首先检查该会话是否有活跃的流
          if (streamManager.hasActiveStream(messageConversationId)) {
            // 从缓存中获取该会话的最新消息列表
            let savedList = conversationMessagesCache.current.get(
              messageConversationId,
            );
            if (!savedList) {
              const streamState = streamManager.getStreamState(
                messageConversationId,
              );
              savedList = streamState?.messageList || [];
            }

            // 累加新内容
            const newList = updateMessageListInternal(savedList);

            // 保存到缓存和StreamManager（确保两者同步）
            conversationMessagesCache.current.set(
              messageConversationId,
              newList,
            );
            streamManager.saveMessageList(messageConversationId, newList);
          }
        }
      }
    }

    function onError(e: any) {
      if (e.type !== "error") {
        return;
      }

      // 尝试从错误事件中获取conversation_id
      let errorConversationId = currentConversationIdRef.current;
      try {
        const data = (e as any).data;
        if (typeof data === "string") {
          const parsed = JSON.parse(data);
          if (parsed?.result?.conversation_id) {
            errorConversationId = parsed.result.conversation_id;
          }
        }
      } catch {
        // 解析失败，使用当前会话ID
      }

      const errMessage = parseErrorData(e.data || "");

      // 只有当错误属于当前活跃会话时，才更新UI
      if (errorConversationId === currentConversationIdRef.current) {
        updateAssistantMessage({
          finish_reason:
            ChatConversationsResponseFinishReasonEnum.FinishReasonUnknown,
          errMessage,
        });
        setIS_STREAMING(false);
        closeSSE();
      }

      // 清理发生错误的会话的流管理空间
      if (errorConversationId) {
        streamManager.closeAndCleanup(errorConversationId);
        conversationMessagesCache.current.delete(errorConversationId);
      }
      sessionStorage.removeItem(CHAT_RESUME_CONVERSATION_KEY);
    }

    function onTimeout(e: any) {
      if (e.type !== "timeout") {
        return;
      }
      onError({ type: "error", data: e.data });
    }

    // 支持用 id 或 history_id 查找，或直接传 index；避免历史消息只有 history_id 时更新不到
    function updateAssistantMessage(data: any, id?: string, index?: number) {
      setMessageList((list) => {
        const newList = [...list];
        const targetIndex =
          index !== undefined
            ? index
            : id
              ? newList.findIndex(
                  (msg) => msg.id === id || msg.history_id === id,
                )
              : newList.length - 1;
        if (targetIndex >= 0) {
          newList[targetIndex] = { ...newList[targetIndex], ...data };
        }
        return newList;
      });
      if (!id) {
        if (isMouseScrollingRef.current) {
          scrollToEnd();
        }
      }
    }

    function scrollToEnd() {
      if (!isMouseScrollingRef.current) {
        return;
      }
      requestAnimationFrame(() => {
        const container = chatContentRef.current;
        if (container) {
          container.scrollTop = container.scrollHeight;
        }
      });
    }

    function replaceMessageList(id: string, list: any[]) {
      // 先保存当前会话的消息列表（如果有活跃流）
      const previousConversationId = currentConversationIdRef.current;
      if (previousConversationId && previousConversationId !== id) {
        // 清除保存定时器，立即保存当前状态
        if (saveTimerRef.current) {
          clearTimeout(saveTimerRef.current);
          saveTimerRef.current = null;
        }

        // 如果当前会话有活跃流，立即保存当前的消息列表
        if (streamManager.hasActiveStream(previousConversationId)) {
          conversationMessagesCache.current.set(
            previousConversationId,
            messageListRef.current,
          );
          streamManager.saveMessageList(
            previousConversationId,
            messageListRef.current,
          );
        }

        // 清理旧会话的活跃状态
        streamManager.setActiveConversation(null);
      }

      // 更新当前会话ID
      currentConversationIdRef.current = id;

      // 设置新的活跃会话
      streamManager.setActiveConversation(id || null);

      // 检查是否有活跃的流需要恢复
      if (id && streamManager.hasActiveStream(id)) {
        // 恢复流的回调
        const callbacks: Record<string, (event: CustomEvent) => void> = {
          message: (event) => onMessage(event),
          error: (event) => onError(event),
          timeout: (event) => onTimeout(event),
        };
        streamManager.restoreStreamCallbacks(id, callbacks);

        // 恢复流状态到消息列表
        const streamState = streamManager.getStreamState(id);
        if (streamState) {
          // 优先使用缓存中的消息列表
          const cachedList = conversationMessagesCache.current.get(id);

          if (cachedList && cachedList.length > 0) {
            // 如果缓存中有，使用缓存（最新的内容）
            const savedList = [...cachedList];
            // 更新最后一条助手消息的状态元数据
            const lastIndex = savedList.length - 1;
            if (savedList[lastIndex]?.role === RoleTypes.ASSISTANT) {
              savedList[lastIndex] = {
                ...savedList[lastIndex],
                sources: streamState.sources || savedList[lastIndex].sources,
                finish_reason: streamState.finish_reason,
                id: streamState.messageId || savedList[lastIndex].id,
                history_id:
                  streamState.history_id || savedList[lastIndex].history_id,
              };
            }
            messageListRef.current = savedList;
            setMessageList(savedList);
            setLoading(true);
            // 如果流还在进行中，设置 IS_STREAMING 为 true
            if (
              streamState.finish_reason ===
              ChatConversationsResponseFinishReasonEnum.FinishReasonUnspecified
            ) {
              setIS_STREAMING(true);
            }
          } else if (
            streamState.messageList &&
            streamState.messageList.length > 0
          ) {
            // 如果缓存中没有，使用streamState保存的消息列表
            const savedList = [...streamState.messageList];
            const lastIndex = savedList.length - 1;
            if (savedList[lastIndex]?.role === RoleTypes.ASSISTANT) {
              savedList[lastIndex] = {
                ...savedList[lastIndex],
                sources: streamState.sources || savedList[lastIndex].sources,
                finish_reason: streamState.finish_reason,
                id: streamState.messageId || savedList[lastIndex].id,
                history_id:
                  streamState.history_id || savedList[lastIndex].history_id,
              };
            }
            messageListRef.current = savedList;
            setMessageList(savedList);
            setLoading(true);
            // 如果流还在进行中，设置 IS_STREAMING 为 true
            if (
              streamState.finish_reason ===
              ChatConversationsResponseFinishReasonEnum.FinishReasonUnspecified
            ) {
              setIS_STREAMING(true);
            }
          } else {
            // 如果没有保存的消息列表，使用服务器返回的历史消息
            messageListRef.current = list;
            setMessageList(list);
            if (
              streamState.finish_reason ===
              ChatConversationsResponseFinishReasonEnum.FinishReasonUnspecified
            ) {
              setLoading(true);
              setIS_STREAMING(true);
            }
          }
        } else {
          messageListRef.current = list;
          setMessageList(list);
        }
      } else {
        // 没有活跃流，优先使用缓存中的最新内容
        if (id) {
          const cachedList = conversationMessagesCache.current.get(id);
          if (cachedList && cachedList.length > 0) {
            messageListRef.current = cachedList;
            setMessageList(cachedList);
          } else {
            messageListRef.current = list;
            setMessageList(list);
          }
        } else {
          messageListRef.current = list;
          setMessageList(list);
        }
        closeSSE();
      }

      // 通知父组件会话ID已更改
      if (onConversationIdChange) {
        onConversationIdChange(id);
      }

      scrollToEnd();
    }

    function createNewChat() {
      // 清空上传的文件（包括 ChatInput 组件内部的文件列表和 store 中的待发送消息）
      chatInputRef.current?.clearFiles();
      // 同时清空 newChatContainer 自己保存的 fileList 状态
      setFileList([]);
      // 清空 store 中的 pendingMessage，防止 useEffect 重新触发 sendMessage
      clearStorePendingMessage();

      // 先保存当前会话的消息列表（如果有活跃流）
      const previousConversationId = currentConversationIdRef.current;
      if (previousConversationId) {
        // 清除保存定时器，立即保存当前状态
        if (saveTimerRef.current) {
          clearTimeout(saveTimerRef.current);
          saveTimerRef.current = null;
        }

        // 如果当前会话有活跃流，立即保存当前的消息列表
        if (streamManager.hasActiveStream(previousConversationId)) {
          conversationMessagesCache.current.set(
            previousConversationId,
            messageListRef.current,
          );
          streamManager.saveMessageList(
            previousConversationId,
            messageListRef.current,
          );
        }

        // 清理旧会话的活跃状态
        streamManager.setActiveConversation(null);
      }

      // 清空当前会话ID
      currentConversationIdRef.current = "";

      // 新增对话时，模型选择重置为默认（LazyRAG）
      resetForNewChat();

      // 清空消息列表和loading状态
      setMessageList([]);
      messageListRef.current = [];
      setLoading(false);
      setIS_STREAMING(false);

      // 清空当前SSE引用（但不关闭连接，让旧会话在后台继续）
      sseRef.current = null;

      // 通知父组件清空sessionId
      if (onConversationIdChange) {
        onConversationIdChange("");
      }

      // 切换到新建对话页面
      setIsChatContent(false);
    }

    function stopGeneration() {
      // 真正关闭SSE流，彻底清理所有数据
      const conversationId = currentConversationIdRef.current;

      // 1. 调用接口通知服务端停止生成
      if (conversationId) {
        ChatServiceApi()
          .conversationServiceStopChatGeneration({
            stopChatGenerationRequest: { conversation_id: conversationId },
          })
          .catch((err) =>
            console.error("Error calling stopChatGeneration:", err),
          );
      }

      // 2. 如果有本地SSE引用，关闭它
      if (sseRef.current) {
        try {
          sseRef.current.close();
        } catch (error) {
          console.error("Error closing SSE:", error);
        }
      }

      // 3. 更新消息状态为已停止
      updateAssistantMessage({
        finish_reason:
          ChatConversationsResponseFinishReasonEnum.FinishReasonStop,
      });

      // 4. 清理本地状态
      setIS_STREAMING(false);
      closeSSE();

      // 5. 彻底清理该会话的流管理空间和缓存
      if (conversationId) {
        streamManager.closeAndCleanup(conversationId);
        conversationMessagesCache.current.delete(conversationId);
      }
      sessionStorage.removeItem(CHAT_RESUME_CONVERSATION_KEY);
    }

    function regenerate() {
      if (loading) {
        return;
      }

      // 🔧 在重新生成前，清理当前会话的旧缓存和流状态
      const currentId = currentConversationIdRef.current;
      if (currentId) {
        // 清理streamManager中的旧流状态
        streamManager.closeAndCleanup(currentId);
        // 清理conversationMessagesCache中的旧缓存
        conversationMessagesCache.current.delete(currentId);
      }

      // 创建一个全新的空助手消息，清理所有旧数据
      const assistantMessage = {
        role: RoleTypes.ASSISTANT,
        delta: "",
        reasoning_content: "",
        finish_reason:
          ChatConversationsResponseFinishReasonEnum.FinishReasonUnspecified,
        answers: [],
        sources: [],
        history_id: undefined,
        id: undefined,
        feed_back: undefined,
        selected_answer_index: undefined,
        answer_preference: undefined,
      };
      const newList = [...messageList];
      newList[newList.length - 1] = assistantMessage;
      messageListRef.current = newList;
      setMessageList(newList);

      // 🔧 更新缓存和streamManager
      if (currentId) {
        conversationMessagesCache.current.set(currentId, newList);
        streamManager.saveMessageList(currentId, newList);
      }

      const userMessage = messageList.findLast(
        (item: any) => item.role === RoleTypes.USER,
      );
      isMouseScrollingRef.current = true;
      openSSE(
        userMessage?.inputs,
        ChatConversationsRequestActionEnum.ChatActionRegeneration,
      );
    }

    function renderText(item: any, uniqueKey?: string) {
      // 生成唯一的 key，用于标识这个思考过程
      // 优先使用传入的 uniqueKey，否则使用 item 的 history_id 或 id
      const thinkingKey = uniqueKey || item.history_id || item.id || "default";
      const isCollapsed = thinkingCollapseMap.get(thinkingKey) || false;

      const toggleCollapse = () => {
        setThinkingCollapseMap((prev) => {
          const newMap = new Map(prev);
          newMap.set(thinkingKey, !isCollapsed);
          return newMap;
        });
      };
      return (
        <Flex vertical>
          {item.images && <ChatImages images={item.images} />}
          {item.files && <ChatFiles files={item.files} />}
          {item.reasoning_content && (
            <>
              <div className="chat-think-status" onClick={toggleCollapse}>
                <img src={ThinkIcon} className="chat-think-icon" />
                <span className="chat-think-title">
                  {item.delta ? "已深度思考" : "思考中"}
                  {(item.thinking_duration_s || item.thinking_time_s) &&
                    item.thinking_duration_s !== "0" &&
                    item.thinking_time_s !== "0" &&
                    ` (${item.thinking_duration_s || item.thinking_time_s}s)`}
                </span>
                {isCollapsed ? (
                  <UpOutlined className="chat-arrow-icon" />
                ) : (
                  <DownOutlined className="chat-arrow-icon" />
                )}
              </div>
              <div className={isCollapsed ? "chat-collapse" : "chat-expand"}>
                <div className="chat-think-text">
                  <MarkdownViewer
                    sources={item.sources}
                    IS_STREAMING={
                      item.finish_reason !==
                      ChatConversationsResponseFinishReasonEnum.FinishReasonStop
                    }
                  >
                    {item.reasoning_content}
                  </MarkdownViewer>
                </div>
                {!item.delta &&
                  item.finish_reason !==
                    ChatConversationsResponseFinishReasonEnum.FinishReasonStop && (
                    <Spin />
                  )}
              </div>
            </>
          )}
          <div className="chat-text">
            <MarkdownViewer
              sources={item.sources}
              IS_STREAMING={
                item.finish_reason !==
                ChatConversationsResponseFinishReasonEnum.FinishReasonStop
              }
            >
              {item.delta}
            </MarkdownViewer>
          </div>
        </Flex>
      );
    }

    const handleScroll = () => {
      const el = chatContentRef.current;
      if (!el) {
        return;
      }
      const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
      const hasScrollbar = el.scrollHeight > el.clientHeight + 2;
      setShowScrollButton(hasScrollbar && distance > 10);
      if (distance <= 10) {
        // 已经触底→立即恢复自动跟随
        isMouseScrollingRef.current = true;
      } else {
        isMouseScrollingRef.current = false;
      }
    };

    const handleToBottom = () => {
      const el = chatContentRef.current;
      if (!el) {
        return;
      }
      isMouseScrollingRef.current = true;
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
      // 按钮点击后立即隐藏
      const hasScrollbar = el.scrollHeight > el.clientHeight + 2;
      setShowScrollButton(hasScrollbar && false);
    };

    useEffect(() => {
      // 内容变化或首次渲染时，计算是否需要显示按钮
      const el = chatContentRef.current;
      if (!el) {
        return;
      }
      const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
      const hasScrollbar = el.scrollHeight > el.clientHeight + 2;
      setShowScrollButton(hasScrollbar && distance > 10);
    }, [messageList]);

    useEffect(() => {
      // 动态设置 ChatInput 高度到 CSS 变量
      const updateInputHeight = () => {
        const inputElement = chatInputRef.current?.element;
        if (inputElement) {
          const height = inputElement.offsetHeight;
          setInputHeight(height + 20);
          document.documentElement.style.setProperty(
            "--chat-input-height",
            `${height + 20}px`,
          );
        }
      };

      // 初始设置
      updateInputHeight();

      // 监听窗口大小变化
      window.addEventListener("resize", updateInputHeight);

      // 使用 MutationObserver 监听 ChatInput 高度变化
      const observer = new MutationObserver(() => {
        updateInputHeight();
      });

      if (chatInputRef.current?.element) {
        observer.observe(chatInputRef.current.element, {
          attributes: true,
          childList: true,
          subtree: true,
          attributeFilter: ["style", "class"],
        });
      }

      return () => {
        window.removeEventListener("resize", updateInputHeight);
        observer.disconnect();
      };
    }, []);

    const handleInputHeightChange = () => {
      const inputElement = chatInputRef.current?.element;
      if (inputElement) {
        const height = inputElement.offsetHeight;
        setInputHeight(height + 20);
        document.documentElement.style.setProperty(
          "--chat-input-height",
          `${height + 20}px`,
        );
      }
    };

    return (
      <div className="chat-chat-container">
        <div className="chat-box">
          <MessageList
            messageList={messageList}
            initialCard={initialCard}
            sendMessage={(text, clearInput) => {
              sendMessage({ text, clearInput });
            }}
            regenerate={regenerate}
            stopGeneration={stopGeneration}
            renderText={renderText}
            updateAssistantMessage={updateAssistantMessage}
            onScroll={handleScroll}
            chatContentRef={chatContentRef}
            sessionId={sessionId}
            onPreferenceSelect={handlePreferenceSelect}
          />

          {messageList.length > 0 && (
            <div
              style={{ bottom: inputHeight }}
              className={`toBottomContainer ${!showScrollButton ? "hidden" : ""}`}
            >
              <span className="toBottom" onClick={handleToBottom}>
                <DoubleRightOutlined
                  style={{
                    fontSize: 18,
                    cursor: "pointer",
                    color: "#8d9ab2",
                    transform: "rotate(90deg)",
                  }}
                />
              </span>
            </div>
          )}

          <ChatInput
            value={content}
            onChange={setContent}
            onSend={sendMessage}
            openHistory={() => setShowHistoryList(true)}
            isChatContent={true}
            showHistoryList={showHistoryList}
            openNewChat={createNewChat}
            ref={chatInputRef}
            onHeightChange={handleInputHeightChange}
            chatConfig={chatConfig}
            setChatConfig={setChatConfig}
            setChatConfigFn={setChatConfigFn}
            sessionId={sessionId}
            isStreaming={IS_STREAMING}
          />
        </div>
      </div>
    );
  },
);

ChatContainerComponent.displayName = "ChatContainerComponent";

export default ChatContainerComponent;

import {
  useRef,
  useState,
  useEffect,
  forwardRef,
  useImperativeHandle,
  ReactElement,
} from "react";
import { Button, Spin, Input, Flex, Badge } from "antd";
import {
  PlusSquareOutlined,
  SendOutlined,
  DownOutlined,
  UpOutlined,
  FileImageOutlined,
  FileTextOutlined,
  EditOutlined,
} from "@ant-design/icons";
import {
  ChatConversationsRequestActionEnum,
  ChatConversationsResponseFinishReasonEnum,
  Conversation,
  Query,
  Source,
} from "@/api/generated/chatbot-client";
import { RcFile } from "antd/es/upload";
import RiskTip from "../RiskTip";
import UIUtils from "@/modules/chat/utils/ui";
import { RoleTypes } from "@/modules/chat/constants/common";
import "./index.scss";
import MarkdownViewer from "@/modules/chat/components/MarkdownViewer";
import ImageUpload, { ImageUploadImperativeProps } from "../ImageUpload";
import PromptModal, { PromptImperativeProps } from "../PromptModal";
import AssistantMessage from "../AssistantMessage";
import { fileToBase64 } from "@/modules/chat/utils/upload";
import ChatImages, { ChatImage } from "../ChatImages";
import ChatFiles, { ChatFile } from "../ChatFiles";
import BatchChatComponent, { BatchChatImperativeProps } from "../BatchChat";
import { streamManager } from "@/modules/chat/utils/StreamManager";
import { ChatServiceApi } from "@/modules/chat/utils/request";
import dayjs from "dayjs";

const ThinkIcon = new URL("../../assets/images/think.png", import.meta.url)
  .href;

export interface ChatImperativeProps {
  replaceMessageList: (id: string, data: any[]) => void;
  createNewChat: () => void;
}

const { TextArea } = Input;

interface Props {
  canChat?: boolean;
  initialCard?: ReactElement | string;
  onOpenSSE: (
    input: any[],
    action: ChatConversationsRequestActionEnum,
    callbacks: Record<string, (e: CustomEvent) => void>,
  ) => any; // Return new SSE.
  onConversationIdChange?: (conversationId: string) => void;
  onCreateNewChat?: () => void;
  onNewConversationCreated?: (conversationId: string) => void; // 当收到新会话的conversation_id时调用
  parseErrorData: (data: string) => string;
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
  create_time?: string;
  answers?: Array<{
    content: string;
    index: number;
    history_id?: string;
    reasoning_content?: string;
    sources?: Source[];
    thinking_duration_s?: string;
  }>;
}

const ChatContainerComponent = forwardRef<ChatImperativeProps, Props>(
  (
    {
      canChat = true,
      initialCard,
      onOpenSSE,
      onConversationIdChange,
      onCreateNewChat,
      onNewConversationCreated,
      parseErrorData,
    },
    ref,
  ) => {
    const batchChatTask = localStorage.getItem("batchChatTask");
    const isMouseScrollingRef = useRef(false);
    const sseRef = useRef<any>(null);
    const imageRef = useRef<ImageUploadImperativeProps | null>(null);
    const fileRef = useRef<ImageUploadImperativeProps | null>(null);
    const promptRef = useRef<PromptImperativeProps | null>(null);
    const batchChatRef = useRef<BatchChatImperativeProps | null>(null);
    const currentConversationIdRef = useRef<string>("");
    const messageListRef = useRef<any[]>([]); // 使用ref保存最新的消息列表，避免闭包问题
    const saveTimerRef = useRef<number | null>(null); // 用于节流保存
    // 为每个会话维护独立的消息缓存，避免后台会话累加时使用旧数据
    const conversationMessagesCache = useRef<Map<string, any[]>>(new Map());
    // 跟踪新创建的会话ID，用于在收到服务器确认时刷新会话历史
    const newConversationIdsRef = useRef<Set<string>>(new Set());

    const [showDot, setShowDot] = useState(batchChatTask);

    const [messageList, setMessageList] = useState<any[]>([]);
    const [loading, setLoading] = useState(false);
    const [content, setContent] = useState("");
    const [isThinkingCollapse, setIsThinkingCollapse] = useState(false);
    const [imageList, setImageList] = useState<ChatImage[]>([]);
    const [fileList, setFileList] = useState<ChatFile[]>([]);

    const IMAGE_MAX_COUNT = 2;
    const IMAGE_MAX_TIPS = `最多上传 ${IMAGE_MAX_COUNT} 张图片`;
    const FILE_MAX_COUNT = 6;
    const FILE_MAX_TIPS = `最多上传 ${FILE_MAX_COUNT} 个文件`;
    const allowedImageTypes = [".png", ".jpg", ".jpeg"];
    const allowedFileTypes = [".pdf", ".docx", ".doc", ".pptx"];

    useImperativeHandle(ref, () => ({
      replaceMessageList,
      createNewChat,
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

        // 组件卸载时，清理所有已完成流的资源
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
      setImageList([]);
      imageRef.current?.clear();
      setFileList([]);
      fileRef.current?.clear();
    }

    // 🆕 自动选择上一轮的第一个答案（如果有多个答案且未选择）
    // 返回更新后的消息列表，如果不需要更新则返回原列表
    function autoSelectPreviousAnswerInList(currentMessages: any[]) {
      // 从最后往前找，找到最后一条助手消息的索引
      let lastAssistantMessageIndex = -1;
      for (let i = currentMessages.length - 1; i >= 0; i--) {
        if (currentMessages[i].role === RoleTypes.ASSISTANT) {
          lastAssistantMessageIndex = i;
          break;
        }
      }

      if (lastAssistantMessageIndex === -1) {
        return currentMessages; // 没有助手消息，返回原列表
      }

      const lastAssistantMessage = currentMessages[lastAssistantMessageIndex];

      // 检查是否有多个答案
      const hasMultipleAnswers =
        lastAssistantMessage.answers &&
        Array.isArray(lastAssistantMessage.answers) &&
        lastAssistantMessage.answers.length >= 2;

      if (!hasMultipleAnswers) {
        return currentMessages; // 没有多个答案，返回原列表
      }

      // 检查是否已经选择过
      if (
        lastAssistantMessage.selected_answer_index !== undefined &&
        lastAssistantMessage.selected_answer_index !== null
      ) {
        return currentMessages; // 已经选择过，返回原列表
      }

      // 检查是否已经生成完成
      if (
        lastAssistantMessage.finish_reason !==
        ChatConversationsResponseFinishReasonEnum.FinishReasonStop
      ) {
        return currentMessages; // 还在生成中，返回原列表
      }

      // 自动选择第一个答案（索引0）
      const selectedIndex = 0;
      const allAnswers = lastAssistantMessage.answers;
      const selectedAnswer = allAnswers[selectedIndex];
      const selectedHistoryId = selectedAnswer.history_id;

      // 获取需要删除的其他答案的 history_id
      const deletedHistoryIds = allAnswers
        .filter((_: any, index: number) => index !== selectedIndex)
        .map((answer: any) => answer.history_id);

      // 调用API标记选择（异步，不阻塞发送消息）
      const promises = deletedHistoryIds.map((deletedHistoryId: string) => {
        return ChatServiceApi().conversationServiceSetChatHistory({
          setChatHistoryRequest: {
            deleted_history_id: deletedHistoryId,
            set_history_id: selectedHistoryId,
          } as any,
        });
      });

      // 异步调用API，不阻塞
      Promise.all(promises).catch((error) => {
        console.error("自动选择答案失败:", error);
      });

      // 立即返回更新后的消息列表
      // 将选中回答的内容复制到顶层字段，以便切换到单回复布局时能正确显示
      const newMessageList = [...currentMessages];
      newMessageList[lastAssistantMessageIndex] = {
        ...lastAssistantMessage,
        selected_answer_index: selectedIndex,
        answer_preference: "prefer_first", // 标记为选择了第一个答案
        delta: selectedAnswer.content || "",
        reasoning_content: selectedAnswer.reasoning_content || "",
        sources: selectedAnswer.sources || lastAssistantMessage.sources,
        history_id:
          selectedAnswer.history_id || lastAssistantMessage.history_id,
        thinking_duration_s: selectedAnswer.thinking_duration_s,
      };
      return newMessageList;
    }

    function sendMessage(text: string, clearInput = true) {
      if (loading || !canChat || !text) {
        return;
      }

      const inputs = [
        { input_type: "text", text },
        ...getFileUrls(imageRef.current?.getFiles(), imageList).map((image) => {
          return {
            input_type: "image",
            uri: image.uri || "",
            input_base64: image.base64 || "",
          };
        }),
        ...getFileUrls(fileRef.current?.getFiles()).map((file) => {
          return { input_type: "file", uri: file.uri || "" };
        }),
      ];
      if (clearInput) {
        setContent("");
        clearMultiData();
      }

      // 🆕 在发送新消息前，自动选择上一轮的第一个答案（如果有多个答案且未选择）
      // 这会返回更新后的消息列表
      const messagesWithAutoSelection = autoSelectPreviousAnswerInList(
        messageListRef.current,
      );

      const userMessage = {
        delta: text,
        role: RoleTypes.USER,
        images: imageList,
        files: fileList,
        inputs,
        finish_reason:
          ChatConversationsResponseFinishReasonEnum.FinishReasonStop,
      };
      const assistantMessage = {
        role: RoleTypes.ASSISTANT,
        finish_reason:
          ChatConversationsResponseFinishReasonEnum.FinishReasonUnspecified,
      };
      // ✅ 使用自动选择后的消息列表，一次性更新所有状态
      const newMessageList = [
        ...messagesWithAutoSelection,
        userMessage,
        assistantMessage,
      ];
      messageListRef.current = newMessageList; // 更新ref
      setMessageList(newMessageList);

      isMouseScrollingRef.current = true;
      scrollToEnd();
      openSSE(inputs, ChatConversationsRequestActionEnum.ChatActionNext);

      // 发送消息后，立即保存消息列表（包括用户的问题）
      // 如果有会话ID，立即保存；如果没有，会在收到conversation_id后保存
      if (currentConversationIdRef.current) {
        streamManager.saveMessageList(
          currentConversationIdRef.current,
          newMessageList,
        );
      }
    }

    const openSSE = (
      input: any[],
      action: ChatConversationsRequestActionEnum,
    ) => {
      setLoading(true);
      const callbacks: Record<string, (e: CustomEvent) => void> = {
        message: (e) => onMessage(e),
        error: (e) => onError(e),
        timeout: (e) => onTimeout(e),
      };
      // 重要修复：不要在创建SSE时传入callbacks，避免重复注册监听器
      // 只通过streamManager.registerStream注册一次
      const sse = onOpenSSE(input, action, {});
      sseRef.current = sse;

      // 使用流管理器注册流（唯一注册点）
      // 新对话创建时，父组件已经通过onCreateNewChat生成了UUID，所以currentConversationIdRef.current应该有值
      // 如果没有会话ID，使用临时ID先注册流，等待服务器返回conversation_id后再迁移
      let conversationId = currentConversationIdRef.current;
      if (!conversationId) {
        // 生成临时ID用于注册流，确保消息能被正确处理
        conversationId = `temp_${Date.now()}_${Math.random().toString(36).substring(2, 15)}`;
        currentConversationIdRef.current = conversationId;
      } else if (!conversationId.startsWith("temp_")) {
        // 如果是前端生成的UUID（不是临时ID），标记为新创建的会话
        newConversationIdsRef.current.add(conversationId);
      }

      streamManager.registerStream(conversationId, sse, callbacks);
      streamManager.setActiveConversation(conversationId);
      // 保存当前的消息列表
      streamManager.saveMessageList(conversationId, messageListRef.current);
    };

    function closeSSE() {
      // 不关闭流，只清理本地引用和loading状态
      // 流由StreamManager统一管理，切换会话时不会中断
      sseRef.current = null;
      setLoading(false);
    }

    function onMessage(e: any) {
      const result = UIUtils.jsonParser(e.data)?.result;

      // 检查result是否存在
      if (!result) {
        return;
      }

      // 关键修复：在函数开始时就固定住当前会话ID，避免在处理过程中被切换
      // 这样可以防止竞态条件导致消息被错误分类
      const messageConversationId = result.conversation_id || "";
      const currentConversationIdAtStart = currentConversationIdRef.current;

      // 判断这个消息是否属于当前活跃会话（基于消息到达时的会话ID）
      // 如果当前使用的是临时ID（以temp_开头），且消息有conversation_id，则认为是活跃会话
      // 否则，只有当消息的conversation_id与当前会话ID匹配时，才是活跃会话
      const isUsingTempId = currentConversationIdAtStart.startsWith("temp_");
      const isActiveConversation = messageConversationId
        ? messageConversationId === currentConversationIdAtStart ||
          (isUsingTempId && messageConversationId)
        : currentConversationIdAtStart === "";

      // 关键修复：只在活跃会话第一次收到conversation_id时才更新状态
      // 后台会话的conversation_id不应该影响当前会话
      const isFirstTimeReceivingId =
        result.conversation_id &&
        result.conversation_id !== currentConversationIdRef.current &&
        isActiveConversation;

      // 如果是新创建的会话（前端生成的UUID），且服务器返回的conversation_id与前端生成的一致，也需要刷新
      const isNewConversationFromFrontend =
        result.conversation_id &&
        newConversationIdsRef.current.has(result.conversation_id) &&
        result.conversation_id === currentConversationIdRef.current &&
        isActiveConversation;

      if (isFirstTimeReceivingId || isNewConversationFromFrontend) {
        if (onConversationIdChange) {
          onConversationIdChange(result.conversation_id);
        }

        // 更新当前会话ID（只有活跃会话才更新）
        const previousConversationId = currentConversationIdRef.current;
        const isPreviousTempId = previousConversationId.startsWith("temp_");
        const isNewConversation =
          isPreviousTempId || previousConversationId !== result.conversation_id;

        if (isFirstTimeReceivingId) {
          currentConversationIdRef.current = result.conversation_id;
          streamManager.setActiveConversation(result.conversation_id);
        }

        // 如果之前使用的是临时ID，需要将临时ID的流迁移到真实ID
        if (isPreviousTempId && sseRef.current && isFirstTimeReceivingId) {
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
          const streamCallbacks: Record<string, (event: CustomEvent) => void> =
            {
              message: (event) => onMessage(event),
              error: (event) => onError(event),
              timeout: (event) => onTimeout(event),
            };
          streamManager.registerStream(
            result.conversation_id,
            sseRef.current,
            streamCallbacks,
          );

          // 注册流后，立即保存当前的消息列表（包括用户的问题）
          const currentList = messageListRef.current;
          conversationMessagesCache.current.set(
            result.conversation_id,
            currentList,
          );
          streamManager.saveMessageList(result.conversation_id, currentList);
        }

        // 如果是新创建的会话，通知父组件刷新会话历史
        // 1. 从临时ID迁移到真实ID
        // 2. 服务器返回的conversation_id与前端生成的不同
        // 3. 前端生成的UUID，服务器返回的conversation_id与前端生成的一致（第一次收到）
        if (
          (isNewConversation || isNewConversationFromFrontend) &&
          onNewConversationCreated
        ) {
          onNewConversationCreated(result.conversation_id);
          // 清除标记，避免重复刷新
          newConversationIdsRef.current.delete(result.conversation_id);
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

      // 关键：当流结束时（finish_reason不是UNSPECIFIED），延迟清理该会话的所有数据
      if (
        result.finish_reason !==
        ChatConversationsResponseFinishReasonEnum.FinishReasonUnspecified
      ) {
        // 只有活跃会话结束时才清理本地SSE引用和loading状态
        if (isActiveConversation) {
          closeSSE();
        }

        // 延迟清理StreamManager中的流（但保留缓存，供切换回来时显示）
        const cleanupConversationId =
          messageConversationId || currentConversationIdAtStart;
        if (cleanupConversationId) {
          setTimeout(() => {
            // 1. 清理StreamManager中的流和状态（关闭SSE连接）
            streamManager.closeAndCleanup(cleanupConversationId);
          }, 1000); // 1秒延迟，确保UI已完全更新
        }
      }

      // 定义一个通用的消息列表更新函数，用于累加delta和reasoning_content
      const updateMessageListInternal = (list: any[]) => {
        const newList = [...list];
        let assistantMessage =
          newList.length > 0 ? newList[newList.length - 1] : null;

        // 如果最后一条不是助手消息，创建一个新的助手消息
        if (
          !assistantMessage ||
          assistantMessage.role !== RoleTypes.ASSISTANT
        ) {
          assistantMessage = {
            role: RoleTypes.ASSISTANT,
            delta: "",
            reasoning_content: "",
            finish_reason:
              ChatConversationsResponseFinishReasonEnum.FinishReasonUnspecified,
          };
          newList.push(assistantMessage);
        }

        // 先保存之前的delta和reasoning_content，避免被result覆盖
        const previousDelta = assistantMessage.delta || "";
        const previousReasoningContent =
          assistantMessage.reasoning_content || "";

        // 保存之前的second_开头的字段（用于累加）
        const previousSecondDelta = assistantMessage.second_result || "";
        const previousSecondReasoningContent =
          assistantMessage.second_reasoning_content || "";

        // 先累加delta和reasoning_content，然后再展开result的其他属性
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
          // 累加 second_ 开头的字段
          second_result: previousSecondDelta + (result.second_result || ""),
          second_reasoning_content:
            previousSecondReasoningContent +
            (result.second_reasoning_content || ""),
          second_id: result.second_id || assistantMessage.second_id,
        };

        // 🆕 如果有 second_result、second_reasoning_content 和 second_id，构建 answers 数组
        if (
          assistantMessage.second_result &&
          assistantMessage.second_reasoning_content &&
          assistantMessage.second_id
        ) {
          assistantMessage.answers = [
            {
              content: assistantMessage.delta || "",
              index: 0,
              history_id: assistantMessage.id || result.messageId,
              reasoning_content: assistantMessage.reasoning_content || "",
              sources: assistantMessage.sources,
              thinking_duration_s: assistantMessage.thinking_duration_s,
            },
            {
              content: assistantMessage.second_result,
              index: 1,
              history_id: assistantMessage.second_id,
              reasoning_content: assistantMessage.second_reasoning_content,
              sources: assistantMessage.sources,
              thinking_duration_s: assistantMessage.second_thinking_duration_s,
            },
          ];
          // 清除顶层的 reasoning_content 和 delta，避免重复显示
          assistantMessage.reasoning_content = "";
          assistantMessage.delta = "";
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

          // 同时更新缓存，确保后台会话切换时能获取到最新数据
          const currentId = currentConversationIdRef.current;
          if (currentId) {
            conversationMessagesCache.current.set(currentId, newList);
          }

          // 使用节流保存消息列表到StreamManager，避免频繁保存导致性能问题
          // 每次流式输出都会触发，但保存操作会被节流到每100ms执行一次
          if (currentId && streamManager.hasActiveStream(currentId)) {
            // 清除之前的定时器
            if (saveTimerRef.current) {
              clearTimeout(saveTimerRef.current);
            }
            // 设置新的定时器，延迟保存
            saveTimerRef.current = setTimeout(() => {
              streamManager.saveMessageList(currentId, messageListRef.current);
              saveTimerRef.current = null;
            }, 100); // 100ms节流，既减少保存频率，又保证及时保存
          }

          return newList;
        });

        if (isMouseScrollingRef.current) {
          scrollToEnd();
        }
      } else {
        // 关键修复：如果不是活跃会话（后台流式输出），也要保存数据
        // 但不更新UI（不调用setMessageList），避免影响当前查看的会话
        if (
          messageConversationId &&
          streamManager.hasActiveStream(messageConversationId)
        ) {
          // 从缓存中获取该会话的最新消息列表
          // 如果缓存中没有，则从StreamManager获取；如果都没有，使用空数组
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

          // 保存到缓存和StreamManager
          conversationMessagesCache.current.set(messageConversationId, newList);
          streamManager.saveMessageList(messageConversationId, newList);
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
        closeSSE();
      }

      // 清理发生错误的会话的流管理空间
      if (errorConversationId) {
        streamManager.closeAndCleanup(errorConversationId);
        conversationMessagesCache.current.delete(errorConversationId);
      }
    }

    function onTimeout(e: any) {
      if (e.type !== "timeout") {
        return;
      }
      onError({ type: "error" });
    }

    // Update answer: If you don't pass the ID, it will be the last one.
    // 支持用 id 或 history_id 查找，避免历史消息只有 history_id 时更新不到
    function updateAssistantMessage(data: any, id?: string) {
      setMessageList((list) => {
        const newList = [...list];
        const index = id
          ? newList.findIndex((msg) => msg.id === id || msg.history_id === id)
          : newList.length - 1;
        if (index >= 0) {
          newList[index] = { ...newList[index], ...data };
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
        const container = document.querySelector(".chat-box");
        if (container) {
          container.scrollTop = container.scrollHeight;
        }
      });
    }

    function replaceMessageList(id: string, list: any[]) {
      // 先保存当前会话的消息列表（如果有活跃流）
      const previousConversationId = currentConversationIdRef.current;
      if (previousConversationId && previousConversationId !== id) {
        // 关键修复：清除保存定时器，立即保存当前状态
        if (saveTimerRef.current) {
          clearTimeout(saveTimerRef.current);
          saveTimerRef.current = null;
        }

        // 如果当前会话有活跃流，立即保存当前的消息列表
        // messageListRef.current 在 onMessage 中已同步更新，直接使用即可
        if (streamManager.hasActiveStream(previousConversationId)) {
          // 立即执行一次保存到缓存和StreamManager，确保最新内容不丢失
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
          // 优先使用缓存中的消息列表，其次使用streamState保存的完整消息列表
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
          } else if (
            streamState.messageList &&
            streamState.messageList.length > 0
          ) {
            // 如果缓存中没有，使用streamState保存的消息列表
            const savedList = [...streamState.messageList];
            // 更新最后一条助手消息的状态元数据（sources, finish_reason等）
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
            messageListRef.current = savedList; // 更新ref
            setMessageList(savedList);
            setLoading(true); // 流还在进行中
          } else {
            // 如果没有保存的消息列表，使用服务器返回的历史消息
            // 注意：这种情况应该很少发生，因为saveMessageList会在每次更新时保存
            messageListRef.current = list; // 更新ref
            setMessageList(list);
            // 如果流还在进行中，设置loading状态
            if (
              streamState.finish_reason ===
              ChatConversationsResponseFinishReasonEnum.FinishReasonUnspecified
            ) {
              setLoading(true);
            }
          }
        } else {
          messageListRef.current = list; // 更新ref
          setMessageList(list);
        }
      } else {
        // 没有活跃流，优先使用缓存中的最新内容（包括已完成的后台流）
        if (id) {
          const cachedList = conversationMessagesCache.current.get(id);
          if (cachedList && cachedList.length > 0) {
            messageListRef.current = cachedList;
            setMessageList(cachedList);
          } else {
            // 缓存中没有，使用服务器返回的历史消息
            messageListRef.current = list;
            setMessageList(list);
          }
        } else {
          messageListRef.current = list;
          setMessageList(list);
        }
        closeSSE();
      }

      if (onConversationIdChange) {
        onConversationIdChange(id);
      }
      scrollToEnd();
    }

    function createNewChat() {
      // 清空上传的文件和图片
      clearMultiData();

      // 如果提供了onCreateNewChat回调，由父组件控制新对话的创建（包括生成UUID）
      if (onCreateNewChat) {
        onCreateNewChat();
        return;
      }

      // 向下兼容：如果没有提供回调，使用原有的空字符串逻辑
      // 1. 先清空当前的消息列表和loading状态，避免显示旧内容
      setMessageList([]);
      messageListRef.current = [];
      setLoading(false);

      // 2. 清空SSE引用（如果有旧的流在进行中）
      if (sseRef.current) {
        // 不要关闭旧流，让它在后台继续（StreamManager会管理）
        sseRef.current = null;
      }

      // 3. 调用replaceMessageList切换到新会话
      replaceMessageList("", []);
    }

    // 批量对话
    function onBatchChat() {
      batchChatRef.current?.onOpen();
    }

    function stopGeneration() {
      // 关键修复：真正关闭SSE流，彻底清理所有数据
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
      closeSSE();

      // 5. 彻底清理该会话的流管理空间和缓存
      if (conversationId) {
        // 立即清理，因为用户主动停止了生成
        streamManager.closeAndCleanup(conversationId);
        conversationMessagesCache.current.delete(conversationId);
      }
    }

    function regenerate() {
      if (loading) {
        return;
      }
      const assistantMessage = {
        role: RoleTypes.ASSISTANT,
        finish_reason:
          ChatConversationsResponseFinishReasonEnum.FinishReasonUnspecified,
      };
      const newList = [...messageList];
      newList[newList.length - 1] = assistantMessage;
      setMessageList(newList);
      const userMessage = messageList.findLast(
        (item: any) => item.role === RoleTypes.USER,
      );
      isMouseScrollingRef.current = true;
      openSSE(
        userMessage?.inputs,
        ChatConversationsRequestActionEnum.ChatActionRegeneration,
      );
    }

    function renderText(item: any) {
      return (
        <Flex vertical>
          {item.images && <ChatImages images={item.images} />}
          {item.files && <ChatFiles files={item.files} />}
          {item.reasoning_content && (
            <>
              <div
                className="chat-think-status"
                onClick={() => {
                  setIsThinkingCollapse(!isThinkingCollapse);
                }}
              >
                <img src={ThinkIcon} className="chat-think-icon" />
                <span className="chat-think-title">
                  {item.delta ? "已深度思考" : "思考中"}{" "}
                  {item.thinking_duration_s &&
                    item.thinking_duration_s !== "0" &&
                    ` (${item.thinking_duration_s}s)`}
                </span>
                {isThinkingCollapse ? (
                  <UpOutlined className="chat-arrow-icon" />
                ) : (
                  <DownOutlined className="chat-arrow-icon" />
                )}
              </div>
              <div
                className={isThinkingCollapse ? "chat-collapse" : "chat-expand"}
              >
                <div className="chat-think-text">
                  <MarkdownViewer sources={item.sources}>
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
            <MarkdownViewer sources={item.sources}>{item.delta}</MarkdownViewer>
          </div>
        </Flex>
      );
    }

    function renderUser(item: any) {
      return (
        <div className="flex items-end justify-end">
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
    }

    const removeImage = (uid: string) => {
      imageRef.current?.removeFile(uid);
      const list = [...imageList].filter((item) => item.uid !== uid);
      setImageList(list);
    };

    const removeFile = (uid: string) => {
      fileRef.current?.removeFile(uid);
      const list = [...fileList].filter((item) => item.uid !== uid);
      setFileList(list);
    };

    const updateImageList = async (list: RcFile[]) => {
      const data: ChatImage[] = [];
      for (let i = 0; i < list.length; i++) {
        const res = await fileToBase64(list[i]);
        data.push({
          uid: list[i].uid,
          base64: res as string,
        });
      }
      setImageList(data);
    };

    const updateFileList = (list: RcFile[]) => {
      const data: ChatFile[] = [];
      for (let i = 0; i < list.length; i++) {
        data.push({
          name: list[i].name,
          uid: list[i].uid,
        });
      }
      setFileList(data);
    };

    const handleScroll = () => {
      const el = document.querySelector(".chat-box") as HTMLElement;

      const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
      // 生成内容瞬间变多， 并数值小可能会导致滚动条不会跟随 暂定40
      if (distance <= 50) {
        // 已经触底→立即恢复自动跟随
        isMouseScrollingRef.current = true;
      } else {
        isMouseScrollingRef.current = false;
      }
    };

    return (
      <div className="chat-chat-container">
        <div className="chat-box" onScroll={handleScroll}>
          <div
            className="message-container chat-content"
            // onWheel={(e) => onChatListWheel(e.deltaY)}
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
                        // 使用 id 或 history_id 定位消息，确保反馈后能正确更新该条消息（避免可二次操作）
                        updateMessage={(
                          msg: Conversation & {
                            id?: string;
                            history_id?: string;
                          },
                        ) =>
                          updateAssistantMessage(msg, msg.id || msg.history_id)
                        }
                      />
                    )}
                  </div>
                );
              })}
            {messageList.length === 0 && initialCard}
          </div>
          <div className="action-container">
            <div className="bottom-bar">
              <Flex gap="8px">
                <Button
                  size="small"
                  className="add-btn"
                  icon={<PlusSquareOutlined />}
                  onClick={createNewChat}
                >
                  新增对话
                </Button>
                {/* TODO: 批量对话任务红点，测试显示 */}
                <Badge dot={showDot === "true"}>
                  <Button
                    size="small"
                    className="add-btn"
                    icon={<PlusSquareOutlined />}
                    onClick={onBatchChat}
                  >
                    批量对话
                  </Button>
                </Badge>
                <Button
                  size="small"
                  className="add-btn"
                  icon={<EditOutlined />}
                  onClick={() => promptRef.current?.onOpen()}
                >
                  提示词模板
                </Button>
                <ImageUpload
                  updateFiles={updateImageList}
                  listNum={imageList.length}
                  ref={imageRef}
                  types={allowedImageTypes}
                  max={IMAGE_MAX_COUNT}
                  maxTips={IMAGE_MAX_TIPS}
                  maxSize={5} // 5 MB
                  icon={
                    <FileImageOutlined
                      style={{
                        cursor: imageList?.length >= 2 ? "no-drop" : "pointer",
                      }}
                    />
                  }
                />
                <ImageUpload
                  updateFiles={updateFileList}
                  listNum={fileList.length}
                  ref={fileRef}
                  types={allowedFileTypes}
                  max={FILE_MAX_COUNT}
                  maxTips={FILE_MAX_TIPS}
                  maxSize={100} // 100 MB
                  icon={
                    <FileTextOutlined
                      style={{
                        cursor: fileList?.length >= 6 ? "no-drop" : "pointer",
                      }}
                    />
                  }
                />
                <RiskTip />
              </Flex>
              <span className="chat-tip">AI生成内容不代表开发者立场</span>
            </div>
            <ChatImages images={imageList} onRemove={removeImage} />
            <ChatFiles files={fileList} onRemove={removeFile} />
            <div
              className={`input-box ${loading || !canChat ? "disabled" : ""}`}
            >
              <TextArea
                className="input"
                value={content}
                placeholder="请输入问题，进行智能问答、图文理解等多种任务，使用 Shift+Enter 换行"
                onPressEnter={(e) => {
                  if (e.shiftKey) {
                    return;
                  }
                  e.preventDefault();
                  sendMessage(content);
                }}
                autoSize={{ minRows: 1, maxRows: 3 }}
                disabled={loading || !canChat}
                onChange={(e) => setContent(e.target.value)}
              />
              <Button
                type="primary"
                shape="round"
                className="submit-btn"
                onClick={() => sendMessage(content)}
                disabled={loading || !content || !canChat}
              >
                <SendOutlined />
              </Button>
            </div>
          </div>
        </div>

        {/* prompt 模板 */}
        <PromptModal
          ref={promptRef}
          onSelectPrompt={(prompt) => setContent(prompt)}
        />

        {/* 批量对话 */}
        <BatchChatComponent
          ref={batchChatRef}
          cancelFn={(bool) => setShowDot(bool)}
        />
      </div>
    );
  },
);

ChatContainerComponent.displayName = "ChatContainerComponent";

export default ChatContainerComponent;

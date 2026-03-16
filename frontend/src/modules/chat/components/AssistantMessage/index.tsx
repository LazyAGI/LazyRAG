import { Avatar, Button, Divider, Flex, message, Spin, Tooltip } from "antd";
import { trim } from "lodash";
import { useEffect, useReducer } from "react";

import "./index.scss";
import {
  CopyOutlined,
  DislikeFilled,
  DislikeOutlined,
  ExclamationCircleOutlined,
  LikeFilled,
  LikeOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import {
  ChatConversationsResponseFinishReasonEnum,
  FeedBackChatHistoryRequestTypeEnum,
  Source,
} from "@/api/generated/chatbot-client";
import { ChatServiceApi } from "@/modules/chat/utils/request";
import MultiAnswerDisplay, { type PreferenceType } from "../MultiAnswerDisplay";
import FeedbackModal from "../FeedbackModal";

const BotAvatarIcon = new URL(
  "../../assets/images/bot_avatar.png",
  import.meta.url,
).href;

// ==================== 类型定义 ====================
interface FeedbackState {
  showModal: boolean; // 反馈弹窗显示状态
  isSubmitting: boolean; // 提交中状态，防止重复提交
  localFeedbackType: string | undefined; // 本地反馈类型，用于立即更新UI
  targetHistoryId: string | undefined; // 当前操作的目标 history_id
}

type FeedbackAction =
  | { type: "OPEN_MODAL"; historyId: string } // 打开反馈弹窗
  | { type: "CLOSE_MODAL" } // 关闭反馈弹窗
  | { type: "SUBMIT_START" } // 开始提交
  | { type: "SUBMIT_SUCCESS"; feedbackType: string } // 提交成功
  | { type: "SUBMIT_FAIL" } // 提交失败
  | { type: "SYNC_FROM_SERVER"; feedbackType: string | undefined }; // 同步服务器状态

// ==================== Reducer ====================
/**
 * 反馈状态管理 Reducer
 * 集中管理所有反馈相关的状态转换逻辑
 */
function feedbackReducer(
  state: FeedbackState,
  action: FeedbackAction,
): FeedbackState {
  switch (action.type) {
    case "OPEN_MODAL":
      return {
        ...state,
        showModal: true,
        targetHistoryId: action.historyId,
      };

    case "CLOSE_MODAL":
      return {
        ...state,
        showModal: false,
        targetHistoryId: undefined,
      };

    case "SUBMIT_START":
      return {
        ...state,
        isSubmitting: true,
      };

    case "SUBMIT_SUCCESS":
      return {
        ...state,
        isSubmitting: false,
        localFeedbackType: action.feedbackType,
        showModal: false,
        targetHistoryId: undefined,
      };

    case "SUBMIT_FAIL":
      return {
        ...state,
        isSubmitting: false,
        targetHistoryId: undefined,
      };

    case "SYNC_FROM_SERVER":
      return {
        ...state,
        localFeedbackType: action.feedbackType,
      };

    default:
      return state;
  }
}

const AssistantMessage = (props: any) => {
  const {
    item,
    index,
    length,
    sendMessage,
    regenerate,
    stopGeneration,
    renderText,
    updateMessage,
    sessionId,
    onPreferenceSelect,
    isLatestDualAnswer,
  } = props;
  // ==================== 状态管理（使用 useReducer） ====================
  const [feedbackState, dispatch] = useReducer(feedbackReducer, {
    showModal: false,
    isSubmitting: false,
    localFeedbackType: item?.feed_back,
    targetHistoryId: undefined,
  });

  // 判断是否已经反馈过（点赞或点踩）
  const hasFeedback =
    feedbackState.localFeedbackType ===
      FeedBackChatHistoryRequestTypeEnum.FeedBackTypeLike ||
    feedbackState.localFeedbackType ===
      FeedBackChatHistoryRequestTypeEnum.FeedBackTypeUnlike;

  // 监听服务器返回的 feed_back，同步更新本地状态（用于刷新页面或切换会话后恢复状态）
  useEffect(() => {
    dispatch({ type: "SYNC_FROM_SERVER", feedbackType: item?.feed_back });
  }, [item?.feed_back]);

  function renderLoading() {
    return (
      <div className="chat-assistant-msg-chat-loading">
        <Spin size="small" />
        <span>{"正在生成回答，请稍候..."}</span>
      </div>
    );
  }

  function renderOnboardingInfo(info: any) {
    return (
      <div className="onboarding-info">
        <div>{info.prologue}</div>
        <ul>
          {info.suggested_questions?.map((question: any, index: any) => {
            if (!question) {
              return null;
            }
            return (
              <li key={index}>
                <a onClick={() => sendMessage(question, false)}>{question}</a>
              </li>
            );
          })}
        </ul>
      </div>
    );
  }

  function renderError() {
    return (
      <div style={{ color: "#b8c3d7" }}>
        <ExclamationCircleOutlined style={{ fontSize: 20 }} />
      </div>
    );
  }

  function renderKnowledgeBase() {
    const sources = item.sources as Source[];
    if (!sources || sources.length < 1) {
      return <></>;
    }
    return (
      <div className="chat-assistant-msg-knowledge-info">
        {Object.values(sources).map((source: Source, sourceIndex: number) => {
          return (
            <div
              className="chat-assistant-msg-knowledge"
              key={source.document_id || `source-${sourceIndex}`}
            >
              <span style={{ marginRight: "8px" }}>{source.index}</span>
              <span
                className="knowledgeName"
                onClick={() => {
                  if (source?.dataset_id === "default") {
                    message.error("临时文件不支持跳转知识库查看");
                    return;
                  }
                  const url = `/appplatform/lib/knowledge/knowledge/${source.dataset_id}/${source.document_id}?group_name=${source.group_name}&segement_id=${source.segement_id}&number=${source.segment_number}&from=chat`;
                  window.open(url, "_blank");
                }}
              >
                {source.file_name}
              </span>
            </div>
          );
        })}
      </div>
    );
  }

  // ==================== 工具函数 ====================
  /**
   * 创建更新后的消息对象（不可变更新，避免直接修改props）
   * @param feedbackType 反馈类型（点赞/点踩）
   * @param targetHistoryId 目标消息的history_id（用于多回答模式）
   * @returns 更新后的新对象
   */
  const createUpdatedItem = (
    feedbackType: FeedBackChatHistoryRequestTypeEnum,
    targetHistoryId?: string,
  ) => {
    if (targetHistoryId && item.answers) {
      // 多回答模式：更新对应答案的 feed_back
      const updatedAnswers = item.answers.map((ans: any) =>
        ans.history_id === targetHistoryId
          ? { ...ans, feed_back: feedbackType }
          : ans,
      );
      return { ...item, answers: updatedAnswers };
    }
    // 单回答模式：更新顶层的 feed_back
    return { ...item, feed_back: feedbackType };
  };

  // ==================== 反馈相关函数 ====================
  /**
   * 处理点赞操作
   * @param type 反馈类型
   * @param historyId 可选，用于多回答模式指定具体答案
   */
  function onFeedBack(
    type: FeedBackChatHistoryRequestTypeEnum,
    historyId?: string,
  ) {
    // 1. 前端拦截：已反馈过的不允许再次操作
    if (hasFeedback) {
      return;
    }

    // 2. 获取目标 history_id
    const targetHistoryId = historyId || item.history_id;
    if (!targetHistoryId) {
      message.error("history_id 不存在，无法提交反馈");
      return;
    }

    // 3. 双回复模式需检查对应答案的反馈状态
    let currentFeedBack: string | undefined;
    if (historyId && item.answers) {
      const answer = item.answers.find(
        (ans: any) => ans.history_id === historyId,
      );
      currentFeedBack = answer?.feed_back || item.feed_back;
    } else {
      currentFeedBack = item.feed_back;
    }

    // 如果已经有反馈状态（点赞或点踩），不允许修改
    if (
      currentFeedBack === FeedBackChatHistoryRequestTypeEnum.FeedBackTypeLike ||
      currentFeedBack === FeedBackChatHistoryRequestTypeEnum.FeedBackTypeUnlike
    ) {
      return;
    }

    dispatch({ type: "SUBMIT_START" });

    // 4. 调用后端 API 提交反馈
    ChatServiceApi()
      .conversationServiceFeedBackChatHistory({
        feedBackChatHistoryRequest: { history_id: targetHistoryId, type },
      })
      .then(() => {
        // 5. 更新父组件状态（不可变更新）
        const updatedItem = createUpdatedItem(type, historyId);
        updateMessage(updatedItem);

        // 6. 提交成功，立即更新本地状态让图标样式即时响应
        dispatch({ type: "SUBMIT_SUCCESS", feedbackType: type });
      })
      .catch(() => {
        message.error("反馈失败，请重试");
        dispatch({ type: "SUBMIT_FAIL" });
      });
  }

  /**
   * 处理点踩按钮点击（显示反馈弹窗）
   * @param historyId 可选，用于多回答模式指定具体答案
   */
  function handleDislikeClick(historyId?: string) {
    // 1. 双回复模式需检查对应答案的反馈状态
    let currentFeedBack: string | undefined;
    if (historyId && item.answers) {
      const answer = item.answers.find(
        (ans: any) => ans.history_id === historyId,
      );
      currentFeedBack = answer?.feed_back || item.feed_back;
    } else {
      currentFeedBack = item.feed_back;
    }

    // 如果已经有反馈状态（点赞或点踩），不允许修改
    if (
      currentFeedBack === FeedBackChatHistoryRequestTypeEnum.FeedBackTypeLike ||
      currentFeedBack === FeedBackChatHistoryRequestTypeEnum.FeedBackTypeUnlike
    ) {
      return;
    }

    // 2. 获取目标 history_id
    const targetHistoryId = historyId || item.history_id;
    if (!targetHistoryId) {
      message.error("history_id 不存在，无法提交反馈");
      return;
    }

    // 3. 打开反馈弹窗并保存 historyId
    dispatch({ type: "OPEN_MODAL", historyId: targetHistoryId });
  }

  /**
   * 处理点踩反馈提交（带原因和期望答案）
   * @param _reasons 不满意的原因列表
   * @param _comment 期望的答案
   */
  function handleFeedbackSubmit(_reasons: string[], _comment: string) {
    // 1. 获取目标 history_id
    const targetHistoryId = feedbackState.targetHistoryId || item.history_id;
    if (!targetHistoryId) {
      message.error("history_id 不存在，无法提交反馈");
      dispatch({ type: "CLOSE_MODAL" });
      return;
    }

    // 2. 防止重复提交
    if (feedbackState.isSubmitting) {
      return;
    }

    // 3. 开始提交
    dispatch({ type: "SUBMIT_START" });

    // 4. 调用后端 API 提交点踩反馈
    ChatServiceApi()
      .conversationServiceFeedBackChatHistory({
        feedBackChatHistoryRequest: {
          history_id: targetHistoryId,
          type: FeedBackChatHistoryRequestTypeEnum.FeedBackTypeUnlike,
          reason: _reasons.join(","),
          expected_answer: _comment,
        } as any,
      })
      .then(() => {
        // 5. 更新父组件状态（不可变更新）
        const updatedItem = createUpdatedItem(
          FeedBackChatHistoryRequestTypeEnum.FeedBackTypeUnlike,
          item.answers ? targetHistoryId : undefined,
        );
        updateMessage(updatedItem);

        // 6. 提交成功，更新状态并关闭弹窗
        dispatch({
          type: "SUBMIT_SUCCESS",
          feedbackType: FeedBackChatHistoryRequestTypeEnum.FeedBackTypeUnlike,
        });
        message.success("感谢您的反馈");
      })
      .catch(() => {
        message.error("反馈提交失败，请重试");
        dispatch({ type: "SUBMIT_FAIL" });
      });
  }

  function onSelectAnswer(selectedIndex: number, preference: PreferenceType) {
    const allAnswers = item.answers || [];
    const selectedAnswer = allAnswers[selectedIndex];
    const selectedHistoryId = selectedAnswer.history_id;

    const deletedHistoryIds = allAnswers
      .filter((_: any, idx: number) => idx !== selectedIndex)
      .map((answer: any) => answer.history_id);

    const promises = deletedHistoryIds.map((deletedHistoryId: string) => {
      return ChatServiceApi().conversationServiceSetChatHistory({
        setChatHistoryRequest: {
          deleted_history_id: deletedHistoryId,
          set_history_id: selectedHistoryId,
        } as any,
      });
    });

    Promise.all(promises)
      .then(() => {
        item.answer_preference = preference;
        item.selected_answer_index = selectedIndex;
        // 将选中回答的内容复制到顶层字段，以便切换到单回复布局时能正确显示
        if (selectedAnswer) {
          item.delta = selectedAnswer.content || "";
          item.reasoning_content = selectedAnswer.reasoning_content || "";
          item.sources = selectedAnswer.sources || item.sources;
          item.history_id = selectedAnswer.history_id || item.history_id;
          item.thinking_duration_s = selectedAnswer.thinking_duration_s;
        }
        updateMessage(item);
        // 回答偏好选择后，更新模型选择并提示（前端处理，不调用后端）
        onPreferenceSelect?.(preference, sessionId);
      })
      .catch(() => {
        message.error("反馈失败，请重试");
      });
  }

  // 为单个回答渲染知识库来源（用于多回答模式）
  function renderAnswerKnowledgeBase(answerIndex: number) {
    const answer = item.answers?.[answerIndex];
    if (!answer) {
      return null;
    }

    const sources = answer.sources as Source[];
    if (!sources || sources.length < 1) {
      return null;
    }

    return (
      <div className="chat-assistant-msg-knowledge-info">
        {Object.values(sources).map((source: Source, sourceIndex: number) => {
          return (
            <div
              className="chat-assistant-msg-knowledge"
              key={source.file_id || `source-${sourceIndex}`}
            >
              <span style={{ marginRight: "8px" }}>{source.index}</span>
              <span
                className="knowledgeName"
                onClick={() => {
                  if (source?.dataset_id === "default") {
                    message.error("临时文件不支持跳转知识库查看");
                    return;
                  }
                  const url = `/appplatform/lib/knowledge/knowledge/${source.dataset_id}/${source.document_id}?group_name=${source.group_name}&segement_id=${source.segement_id}&number=${source.segment_number}&from=chat`;
                  window.open(url, "_blank");
                }}
              >
                {source.file_name}
              </span>
            </div>
          );
        })}
      </div>
    );
  }

  // 为单个回答渲染底部工具栏（用于多回答模式）
  // showFullToolbar: 是否显示完整工具栏（包括重新生成、点赞等），false则只显示复制按钮
  function renderAnswerFooter(answerIndex: number, showFullToolbar = false) {
    const answer = item.answers?.[answerIndex];
    if (!answer) {
      return null;
    }

    // 使用答案的 history_id 和 feed_back
    const answerHistoryId = answer.history_id;
    const answerFeedBack = answer.feed_back || item.feed_back;

    return (
      <>
        <Divider
          className="chat-assistant-msg-tool-divider"
          style={{ margin: "12px 0" }}
        />
        <div className="chat-assistant-msg-tool-chat-toolbar">
          <div>
            <Tooltip title={"复制"}>
              <Button
                className="tool-btn"
                icon={<CopyOutlined />}
                onClick={() => {
                  navigator.clipboard.writeText(answer.content.trim());
                  message.success("复制成功");
                }}
              />
            </Tooltip>
            {showFullToolbar && index === length - 1 && (
              <Tooltip title={"重新生成"}>
                <Button
                  className="tool-btn"
                  icon={<ReloadOutlined />}
                  onClick={regenerate}
                />
              </Tooltip>
            )}
          </div>
          {showFullToolbar && (
            <Flex>
              {answerFeedBack ===
              FeedBackChatHistoryRequestTypeEnum.FeedBackTypeLike ? (
                <LikeFilled
                  className="tool-btn"
                  style={{
                    cursor: "not-allowed",
                    opacity: 0.6,
                    pointerEvents: "none",
                  }}
                />
              ) : (
                <LikeOutlined
                  className="tool-btn"
                  onClick={
                    answerFeedBack ===
                    FeedBackChatHistoryRequestTypeEnum.FeedBackTypeUnlike
                      ? undefined
                      : () =>
                          onFeedBack(
                            FeedBackChatHistoryRequestTypeEnum.FeedBackTypeLike,
                            answerHistoryId,
                          )
                  }
                  style={
                    answerFeedBack ===
                    FeedBackChatHistoryRequestTypeEnum.FeedBackTypeUnlike
                      ? {
                          cursor: "not-allowed",
                          opacity: 0.6,
                          pointerEvents: "none",
                        }
                      : {}
                  }
                />
              )}
              {answerFeedBack ===
              FeedBackChatHistoryRequestTypeEnum.FeedBackTypeUnlike ? (
                <DislikeFilled
                  className="tool-btn"
                  style={{
                    cursor: "not-allowed",
                    opacity: 0.6,
                    pointerEvents: "none",
                  }}
                />
              ) : (
                <DislikeOutlined
                  className="tool-btn"
                  onClick={
                    answerFeedBack ===
                    FeedBackChatHistoryRequestTypeEnum.FeedBackTypeLike
                      ? undefined
                      : () => handleDislikeClick(answerHistoryId)
                  }
                  style={
                    answerFeedBack ===
                    FeedBackChatHistoryRequestTypeEnum.FeedBackTypeLike
                      ? {
                          cursor: "not-allowed",
                          opacity: 0.6,
                          pointerEvents: "none",
                        }
                      : {}
                  }
                />
              )}
            </Flex>
          )}
        </div>
      </>
    );
  }

  // 为单回答模式渲染底部工具栏
  function renderFooter() {
    return (
      <>
        <Divider className="chat-assistant-msg-tool-divider" />
        <div className="chat-assistant-msg-tool-chat-toolbar">
          <div>
            <Tooltip title={"复制"}>
              <Button
                className="tool-btn"
                icon={<CopyOutlined />}
                onClick={() => {
                  navigator.clipboard.writeText(item.delta.trim());
                  message.success("复制成功");
                }}
              />
            </Tooltip>
            {index === length - 1 && (
              <Tooltip title={"重新生成"}>
                <Button
                  className="tool-btn"
                  icon={<ReloadOutlined />}
                  onClick={regenerate}
                />
              </Tooltip>
            )}
          </div>
          <Flex>
            {feedbackState.localFeedbackType ===
            FeedBackChatHistoryRequestTypeEnum.FeedBackTypeLike ? (
              <LikeFilled
                className="tool-btn"
                style={{
                  cursor: "not-allowed",
                  opacity: 0.6,
                  pointerEvents: "none",
                }}
              />
            ) : (
              <LikeOutlined
                className="tool-btn"
                onClick={
                  feedbackState.localFeedbackType ===
                  FeedBackChatHistoryRequestTypeEnum.FeedBackTypeUnlike
                    ? undefined
                    : () =>
                        onFeedBack(
                          FeedBackChatHistoryRequestTypeEnum.FeedBackTypeLike,
                        )
                }
                style={
                  feedbackState.localFeedbackType ===
                  FeedBackChatHistoryRequestTypeEnum.FeedBackTypeUnlike
                    ? {
                        cursor: "not-allowed",
                        opacity: 0.6,
                        pointerEvents: "none",
                      }
                    : {}
                }
              />
            )}
            {feedbackState.localFeedbackType ===
            FeedBackChatHistoryRequestTypeEnum.FeedBackTypeUnlike ? (
              <DislikeFilled
                className="tool-btn"
                style={{
                  cursor: "not-allowed",
                  opacity: 0.6,
                  pointerEvents: "none",
                }}
              />
            ) : (
              <DislikeOutlined
                className="tool-btn"
                onClick={
                  feedbackState.localFeedbackType ===
                  FeedBackChatHistoryRequestTypeEnum.FeedBackTypeLike
                    ? undefined
                    : () => handleDislikeClick()
                }
                style={
                  feedbackState.localFeedbackType ===
                  FeedBackChatHistoryRequestTypeEnum.FeedBackTypeLike
                    ? {
                        cursor: "not-allowed",
                        opacity: 0.6,
                        pointerEvents: "none",
                      }
                    : {}
                }
              />
            )}
          </Flex>
        </div>
      </>
    );
  }

  function renderBottom() {
    if (
      item.finish_reason ===
      ChatConversationsResponseFinishReasonEnum.FinishReasonUnspecified
    ) {
      return (
        <Button className="stop-btn" onClick={stopGeneration}>
          {"停止生成"}
        </Button>
      );
    }
    if (
      item.finish_reason ===
      ChatConversationsResponseFinishReasonEnum.FinishReasonUnknown
    ) {
      return (
        <>
          <span style={{ color: "#b8c3d7" }}>{item.errMessage}</span>
          <Button
            className="stop-btn"
            style={{ marginLeft: 10 }}
            onClick={regenerate}
          >
            {"重新生成"}
          </Button>
        </>
      );
    }
    return null;
  }

  // 检查是否有多个回答
  const hasMultipleAnswers =
    item.answers && Array.isArray(item.answers) && item.answers.length >= 2;

  // 检查多回答模式下是否有内容
  const hasMultipleAnswersContent =
    hasMultipleAnswers &&
    item.answers.some(
      (answer: any) =>
        (answer.content && trim(answer.content)?.length > 0) ||
        (answer.reasoning_content &&
          trim(answer.reasoning_content)?.length > 0),
    );

  // 判断是否应该显示 loading
  const shouldShowLoading =
    !(item.delta && trim(item.delta)?.length > 0) &&
    !(item.reasoning_content && trim(item.reasoning_content)?.length > 0) &&
    !hasMultipleAnswersContent && // 🔥 使用新的判断条件
    item.finish_reason ===
      ChatConversationsResponseFinishReasonEnum.FinishReasonUnspecified;

  // 判断是否应该使用多问答样式：有多个回答且用户还未选择
  const shouldUseMultiAnswerStyle =
    hasMultipleAnswers &&
    (item.selected_answer_index === undefined ||
      item.selected_answer_index === null);

  // 渲染双回复布局
  if (shouldUseMultiAnswerStyle) {
    return (
      <div className="chat-assistant-msg-multi-answer-wrap">
        <Avatar
          className="chat-avatar"
          size={"small"}
          icon={<img src={BotAvatarIcon} />}
        />
        <div className="chat-bot-box-multi">
          <div className="chat-bot">
            {shouldShowLoading
              ? renderLoading()
              : // 多回答模式：只渲染 thinking，不渲染 delta
                renderText({ ...item, delta: "" })}
            {item.finish_reason ===
              ChatConversationsResponseFinishReasonEnum.FinishReasonUnknown &&
              renderError()}

            {/* 显示多回答 - 在流式返回时也显示 */}
            <MultiAnswerDisplay
              key={item.history_id || item.id || `multi-answer-${index}`}
              answers={item.answers}
              showPreference={isLatestDualAnswer}
              renderText={(
                content: string,
                reasoningContent?: string,
                answerIndex?: number,
              ) => {
                // 为每个回答生成唯一的 key
                const answer = item.answers[answerIndex || 0];
                const uniqueKey = answer?.history_id || `answer_${answerIndex}`;

                return renderText(
                  {
                    ...item,
                    delta: content,
                    reasoning_content: reasoningContent,
                    sources: answer?.sources || [], // 使用每个回答独立的 sources
                    thinking_duration_s: answer?.thinking_duration_s, // 使用每个回答独立的思考时间
                  },
                  uniqueKey, // 传入唯一的 key
                );
              }}
              onSelectAnswer={onSelectAnswer}
              disabled={
                item.finish_reason !==
                ChatConversationsResponseFinishReasonEnum.FinishReasonStop
              }
              renderFooter={
                item.finish_reason ===
                ChatConversationsResponseFinishReasonEnum.FinishReasonStop
                  ? renderAnswerFooter
                  : undefined
              }
              renderKnowledgeBase={
                item.finish_reason ===
                ChatConversationsResponseFinishReasonEnum.FinishReasonStop
                  ? renderAnswerKnowledgeBase
                  : undefined
              }
              initialSelectedIndex={item.selected_answer_index}
              initialPreference={item.answer_preference}
              isStreaming={
                item.finish_reason ===
                ChatConversationsResponseFinishReasonEnum.FinishReasonUnspecified
              }
            />
          </div>
          {index === length - 1 && renderBottom()}
        </div>
        <FeedbackModal
          visible={feedbackState.showModal}
          onCancel={() => dispatch({ type: "CLOSE_MODAL" })}
          onSubmit={handleFeedbackSubmit}
          submitLoading={feedbackState.isSubmitting}
        />
      </div>
    );
  }

  // 渲染单回复布局
  return (
    <div className="chat-assistant-msg-single-answer-wrap">
      <Avatar
        className="chat-avatar"
        size={"small"}
        icon={<img src={BotAvatarIcon} />}
      />
      <div className="chat-bot-box-single">
        <div className="chat-bot">
          {shouldShowLoading
            ? renderLoading()
            : item.onboardingInfo
              ? renderOnboardingInfo(item.onboardingInfo)
              : renderText(item)}
          {item.finish_reason ===
            ChatConversationsResponseFinishReasonEnum.FinishReasonUnknown &&
            renderError()}

          {/* 知识库来源 - 单回答模式 */}
          {item.finish_reason ===
            ChatConversationsResponseFinishReasonEnum.FinishReasonStop &&
            !item.onboardingInfo &&
            renderKnowledgeBase()}

          {/* 底部工具栏 - 单回答模式 */}
          {item.finish_reason ===
            ChatConversationsResponseFinishReasonEnum.FinishReasonStop &&
            !item.onboardingInfo &&
            renderFooter()}
        </div>
        {index === length - 1 && renderBottom()}
      </div>
      <FeedbackModal
        visible={feedbackState.showModal}
        onCancel={() => dispatch({ type: "CLOSE_MODAL" })}
        onSubmit={handleFeedbackSubmit}
        submitLoading={feedbackState.isSubmitting}
      />
    </div>
  );
};

export default AssistantMessage;

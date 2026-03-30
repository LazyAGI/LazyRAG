import { Avatar, Button, Divider, Flex, message, Spin, Tooltip } from "antd";
import { trim } from "lodash";
import { useEffect, useReducer } from "react";
import { useTranslation } from "react-i18next";

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

interface FeedbackState {
  showModal: boolean;
  isSubmitting: boolean;
  localFeedbackType: string | undefined;
  targetHistoryId: string | undefined;
}

type FeedbackAction =
  | { type: "OPEN_MODAL"; historyId: string }
  | { type: "CLOSE_MODAL" }
  | { type: "SUBMIT_START" }
  | { type: "SUBMIT_SUCCESS"; feedbackType: string }
  | { type: "SUBMIT_FAIL" }
  | { type: "SYNC_FROM_SERVER"; feedbackType: string | undefined };

// ==================== Reducer ====================

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
  const { t } = useTranslation();
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
  const [feedbackState, dispatch] = useReducer(feedbackReducer, {
    showModal: false,
    isSubmitting: false,
    localFeedbackType: item?.feed_back,
    targetHistoryId: undefined,
  });

  const hasFeedback =
    feedbackState.localFeedbackType ===
      FeedBackChatHistoryRequestTypeEnum.FeedBackTypeLike ||
    feedbackState.localFeedbackType ===
      FeedBackChatHistoryRequestTypeEnum.FeedBackTypeUnlike;

  useEffect(() => {
    dispatch({ type: "SYNC_FROM_SERVER", feedbackType: item?.feed_back });
  }, [item?.feed_back]);

  function renderLoading() {
    return (
      <div className="chat-assistant-msg-chat-loading">
        <Spin size="small" />
        <span>{t("chat.generatingAnswer")}</span>
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
                    message.error(t("chat.tempFileNotSupportJump"));
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

  
  const createUpdatedItem = (
    feedbackType: FeedBackChatHistoryRequestTypeEnum,
    targetHistoryId?: string,
  ) => {
    if (targetHistoryId && item.answers) {
      const updatedAnswers = item.answers.map((ans: any) =>
        ans.history_id === targetHistoryId
          ? { ...ans, feed_back: feedbackType }
          : ans,
      );
      return { ...item, answers: updatedAnswers };
    }
    return { ...item, feed_back: feedbackType };
  };

  
  function onFeedBack(
    type: FeedBackChatHistoryRequestTypeEnum,
    historyId?: string,
  ) {
    if (hasFeedback) {
      return;
    }

    const targetHistoryId = historyId || item.history_id;
    if (!targetHistoryId) {
      message.error(t("chat.historyIdMissingFeedback"));
      return;
    }

    let currentFeedBack: string | undefined;
    if (historyId && item.answers) {
      const answer = item.answers.find(
        (ans: any) => ans.history_id === historyId,
      );
      currentFeedBack = answer?.feed_back || item.feed_back;
    } else {
      currentFeedBack = item.feed_back;
    }

    if (
      currentFeedBack === FeedBackChatHistoryRequestTypeEnum.FeedBackTypeLike ||
      currentFeedBack === FeedBackChatHistoryRequestTypeEnum.FeedBackTypeUnlike
    ) {
      return;
    }

    dispatch({ type: "SUBMIT_START" });

    ChatServiceApi()
      .conversationServiceFeedBackChatHistory({
        feedBackChatHistoryRequest: { history_id: targetHistoryId, type },
      })
      .then(() => {
        const updatedItem = createUpdatedItem(type, historyId);
        updateMessage(updatedItem);

        dispatch({ type: "SUBMIT_SUCCESS", feedbackType: type });
      })
      .catch(() => {
        message.error(t("chat.feedbackFailedRetry"));
        dispatch({ type: "SUBMIT_FAIL" });
      });
  }

  
  function handleDislikeClick(historyId?: string) {
    let currentFeedBack: string | undefined;
    if (historyId && item.answers) {
      const answer = item.answers.find(
        (ans: any) => ans.history_id === historyId,
      );
      currentFeedBack = answer?.feed_back || item.feed_back;
    } else {
      currentFeedBack = item.feed_back;
    }

    if (
      currentFeedBack === FeedBackChatHistoryRequestTypeEnum.FeedBackTypeLike ||
      currentFeedBack === FeedBackChatHistoryRequestTypeEnum.FeedBackTypeUnlike
    ) {
      return;
    }

    const targetHistoryId = historyId || item.history_id;
    if (!targetHistoryId) {
      message.error(t("chat.historyIdMissingFeedback"));
      return;
    }

    dispatch({ type: "OPEN_MODAL", historyId: targetHistoryId });
  }

  
  function handleFeedbackSubmit(_reasons: string[], _comment: string) {
    const targetHistoryId = feedbackState.targetHistoryId || item.history_id;
    if (!targetHistoryId) {
      message.error(t("chat.historyIdMissingFeedback"));
      dispatch({ type: "CLOSE_MODAL" });
      return;
    }

    if (feedbackState.isSubmitting) {
      return;
    }

    dispatch({ type: "SUBMIT_START" });

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
        const updatedItem = createUpdatedItem(
          FeedBackChatHistoryRequestTypeEnum.FeedBackTypeUnlike,
          item.answers ? targetHistoryId : undefined,
        );
        updateMessage(updatedItem);

        dispatch({
          type: "SUBMIT_SUCCESS",
          feedbackType: FeedBackChatHistoryRequestTypeEnum.FeedBackTypeUnlike,
        });
        message.success(t("chat.thanksFeedback"));
      })
      .catch(() => {
        message.error(t("chat.feedbackSubmitFailedRetry"));
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
        if (selectedAnswer) {
          item.delta = selectedAnswer.content || "";
          item.reasoning_content = selectedAnswer.reasoning_content || "";
          item.sources = selectedAnswer.sources || item.sources;
          item.history_id = selectedAnswer.history_id || item.history_id;
          item.thinking_duration_s = selectedAnswer.thinking_duration_s;
        }
        updateMessage(item);
        onPreferenceSelect?.(preference, sessionId);
      })
      .catch(() => {
        message.error(t("chat.feedbackFailedRetry"));
      });
  }

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
                    message.error(t("chat.tempFileNotSupportJump"));
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

  function renderAnswerFooter(answerIndex: number, showFullToolbar = false) {
    const answer = item.answers?.[answerIndex];
    if (!answer) {
      return null;
    }

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
            <Tooltip title={t("chat.copy")}>
              <Button
                className="tool-btn"
                icon={<CopyOutlined />}
                onClick={() => {
                  navigator.clipboard.writeText(answer.content.trim());
                  message.success(t("chat.copySuccess"));
                }}
              />
            </Tooltip>
            {showFullToolbar && index === length - 1 && (
              <Tooltip title={t("chat.regenerate")}>
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

  function renderFooter() {
    return (
      <>
        <Divider className="chat-assistant-msg-tool-divider" />
        <div className="chat-assistant-msg-tool-chat-toolbar">
          <div>
            <Tooltip title={t("chat.copy")}>
              <Button
                className="tool-btn"
                icon={<CopyOutlined />}
                onClick={() => {
                  navigator.clipboard.writeText(item.delta.trim());
                  message.success(t("chat.copySuccess"));
                }}
              />
            </Tooltip>
            {index === length - 1 && (
              <Tooltip title={t("chat.regenerate")}>
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
          {t("chat.stopGenerate")}
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
            {t("chat.regenerate")}
          </Button>
        </>
      );
    }
    return null;
  }

  const hasMultipleAnswers =
    item.answers && Array.isArray(item.answers) && item.answers.length >= 2;

  const hasMultipleAnswersContent =
    hasMultipleAnswers &&
    item.answers.some(
      (answer: any) =>
        (answer.content && trim(answer.content)?.length > 0) ||
        (answer.reasoning_content &&
          trim(answer.reasoning_content)?.length > 0),
    );

  const shouldShowLoading =
    !(item.delta && trim(item.delta)?.length > 0) &&
    !(item.reasoning_content && trim(item.reasoning_content)?.length > 0) &&
    !hasMultipleAnswersContent &&
    item.finish_reason ===
      ChatConversationsResponseFinishReasonEnum.FinishReasonUnspecified;

  const shouldUseMultiAnswerStyle =
    hasMultipleAnswers &&
    (item.selected_answer_index === undefined ||
      item.selected_answer_index === null);

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
              : renderText({ ...item, delta: "" })}
            {item.finish_reason ===
              ChatConversationsResponseFinishReasonEnum.FinishReasonUnknown &&
              renderError()}

            {}
            <MultiAnswerDisplay
              key={item.history_id || item.id || `multi-answer-${index}`}
              answers={item.answers}
              showPreference={isLatestDualAnswer}
              renderText={(
                content: string,
                reasoningContent?: string,
                answerIndex?: number,
              ) => {
                const answer = item.answers[answerIndex || 0];
                const uniqueKey = answer?.history_id || `answer_${answerIndex}`;

                return renderText(
                  {
                    ...item,
                    delta: content,
                    reasoning_content: reasoningContent,
                    sources: answer?.sources || [],
                    thinking_duration_s: answer?.thinking_duration_s,
                  },
                  uniqueKey,
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

          {}
          {item.finish_reason ===
            ChatConversationsResponseFinishReasonEnum.FinishReasonStop &&
            !item.onboardingInfo &&
            renderKnowledgeBase()}

          {}
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

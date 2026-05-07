import { type MouseEvent, type ReactNode, type Ref } from "react";
import { Typography } from "antd";
import {
  CloseOutlined,
  HistoryOutlined,
  MessageOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import {
  ChatComposer,
  ChatMessageStream,
  HistorySessionModal,
  HistorySessionTab,
  NewSessionConfigModal,
  WorkflowStepCard,
} from ".";
import {
  type SelfEvolutionChatMessage,
  type SelfEvolutionCheckpointPrompt,
  type SelfEvolutionHistoryEntry,
  type SelfEvolutionLaunchOptionCard,
  type SelfEvolutionSummaryItem,
} from "./types";
import { type WorkflowStep as SelfEvolutionRuntimeWorkflowStep } from "../shared";

const { Paragraph, Text, Title } = Typography;

type SelfEvolutionSessionSummary = {
  id: string;
  title: string;
};

export type SelfEvolutionWorkbenchViewProps = {
  workflowSteps: SelfEvolutionRuntimeWorkflowStep[];
  activeStepText: string;
  routeThreadId?: string;
  isRestoringThread: boolean;
  threadRestoreError: string;
  activeSession: SelfEvolutionSessionSummary;
  chatSessionsCount: number;
  historySessionEntries: SelfEvolutionHistoryEntry[];
  deletingHistoryKeys: string[];
  displayedMessages: SelfEvolutionChatMessage[];
  chatStreamRef: Ref<HTMLDivElement>;
  isAutoInteractionActive: boolean;
  isSendingMessage: boolean;
  displayedCheckpointWaitPrompt?: SelfEvolutionCheckpointPrompt;
  prompt: string;
  isHistorySessionModalOpen: boolean;
  threadHistoryListError: string;
  isLoadingThreadHistoryList: boolean;
  isNewSessionConfigOpen: boolean;
  newSessionOptionCards: SelfEvolutionLaunchOptionCard[];
  newSessionSummaryItems: SelfEvolutionSummaryItem[];
  isNewSessionStepOneDone: boolean;
  isNewSessionStepTwoDone: boolean;
  isNewSessionStepThreeDone: boolean;
  isNewSessionStepFourDone: boolean;
  isNewSessionConfirmDisabled: boolean;
  isConfirmingNewSession: boolean;
  getStepStatusLabel: (status: SelfEvolutionRuntimeWorkflowStep["status"]) => string;
  renderStepRuntimeSummary: (step: SelfEvolutionRuntimeWorkflowStep) => ReactNode;
  renderStepChildren: (step: SelfEvolutionRuntimeWorkflowStep) => ReactNode;
  renderKnowledgeAndModeTools: () => ReactNode;
  renderSendButton: () => ReactNode;
  onRetryRestoreThread: () => void;
  onCloseSession: (sessionId: string) => void;
  onSelectHistorySession: (entry: Pick<SelfEvolutionHistoryEntry, "sessionId" | "threadId">) => void;
  onDeleteHistorySession: (
    entry: SelfEvolutionHistoryEntry,
    event: MouseEvent<HTMLElement>,
  ) => void;
  onCreateSession: () => void;
  onOpenHistorySessionModal: () => void;
  onPromptChange: (value: string) => void;
  onSend: (command?: string) => void;
  onCloseHistorySessionModal: () => void;
  onRetryThreadHistoryList: () => void;
  onCancelCreateSession: () => void;
  onConfirmCreateSession: () => void;
};

export function SelfEvolutionWorkbenchView({
  workflowSteps,
  activeStepText,
  routeThreadId,
  isRestoringThread,
  threadRestoreError,
  activeSession,
  chatSessionsCount,
  historySessionEntries,
  deletingHistoryKeys,
  displayedMessages,
  chatStreamRef,
  isAutoInteractionActive,
  isSendingMessage,
  displayedCheckpointWaitPrompt,
  prompt,
  isHistorySessionModalOpen,
  threadHistoryListError,
  isLoadingThreadHistoryList,
  isNewSessionConfigOpen,
  newSessionOptionCards,
  newSessionSummaryItems,
  isNewSessionStepOneDone,
  isNewSessionStepTwoDone,
  isNewSessionStepThreeDone,
  isNewSessionStepFourDone,
  isNewSessionConfirmDisabled,
  isConfirmingNewSession,
  getStepStatusLabel,
  renderStepRuntimeSummary,
  renderStepChildren,
  renderKnowledgeAndModeTools,
  renderSendButton,
  onRetryRestoreThread,
  onCloseSession,
  onSelectHistorySession,
  onDeleteHistorySession,
  onCreateSession,
  onOpenHistorySessionModal,
  onPromptChange,
  onSend,
  onCloseHistorySessionModal,
  onRetryThreadHistoryList,
  onCancelCreateSession,
  onConfirmCreateSession,
}: SelfEvolutionWorkbenchViewProps) {
  return (
    <div className="self-evolution-session-page">
      <div className="self-evolution-workbench">
        <section className="self-evolution-workflow-panel" aria-label="执行步骤">
          <div className="self-evolution-workflow-head">
            <Title level={3}>自进化执行编排</Title>
            <Paragraph>当前聚焦：{activeStepText}</Paragraph>
            {routeThreadId && (
              <Text className="self-evolution-detail-thread">
                {`线程 ID：${routeThreadId}${isRestoringThread ? " · 正在恢复详情" : ""}`}
              </Text>
            )}
            {threadRestoreError && routeThreadId && (
              <div className="self-evolution-restore-error" role="alert">
                <span>{threadRestoreError}</span>
                <button type="button" onClick={onRetryRestoreThread}>
                  重试
                </button>
              </div>
            )}
          </div>

          <div className="self-evolution-step-list">
            <div className="self-evolution-step-scroll">
              {workflowSteps.map((step, index) => (
                <WorkflowStepCard
                  key={step.renderKey || step.id}
                  step={step}
                  index={index}
                  statusLabel={getStepStatusLabel(step.status)}
                  runtimeSummary={renderStepRuntimeSummary(step)}
                >
                  {renderStepChildren(step)}
                </WorkflowStepCard>
              ))}
            </div>
          </div>
        </section>

        <section className="self-evolution-chat-panel" aria-label="历史会话窗口">
          <div className="self-evolution-history-shell">
            <div className="self-evolution-history-tabs" aria-label="历史会话标签栏">
              <div className="self-evolution-history-tabs-scroll">
                <button
                  type="button"
                  className="self-evolution-history-tab is-active"
                  title={activeSession.title}
                >
                  <span className="self-evolution-history-tab-icon">
                    <MessageOutlined />
                  </span>
                  <span className="self-evolution-history-tab-content">
                    <span className="self-evolution-history-tab-label">{activeSession.title}</span>
                  </span>
                  {chatSessionsCount > 1 && (
                    <span
                      className="self-evolution-history-tab-close"
                      onClick={(event) => {
                        event.stopPropagation();
                        onCloseSession(activeSession.id);
                      }}
                    >
                      <CloseOutlined />
                    </span>
                  )}
                </button>
                {historySessionEntries.map((entry) => (
                  <HistorySessionTab
                    key={entry.key}
                    entry={entry}
                    isDeleting={deletingHistoryKeys.includes(entry.key)}
                    onSelect={onSelectHistorySession}
                    onDelete={onDeleteHistorySession}
                  />
                ))}
              </div>
              <button
                type="button"
                className="self-evolution-history-tab-create"
                onClick={onCreateSession}
                title="新建会话"
              >
                <PlusOutlined />
                <span>新建</span>
              </button>
              <button
                type="button"
                className="self-evolution-history-tab-fetch"
                onClick={onOpenHistorySessionModal}
                title="打开历史会话列表"
                aria-label="打开历史会话列表"
              >
                <HistoryOutlined />
                <span>历史</span>
              </button>
            </div>
          </div>

          <ChatMessageStream messages={displayedMessages} streamRef={chatStreamRef} />

          <ChatComposer
            activeStepText={activeStepText}
            isAutoInteractionActive={isAutoInteractionActive}
            isSendingMessage={isSendingMessage}
            pendingCheckpointWaitPrompt={displayedCheckpointWaitPrompt}
            prompt={prompt}
            onPromptChange={onPromptChange}
            onSend={onSend}
            renderKnowledgeAndModeTools={renderKnowledgeAndModeTools}
            renderSendButton={renderSendButton}
          />
        </section>

        <HistorySessionModal
          open={isHistorySessionModalOpen}
          threadHistoryListError={threadHistoryListError}
          isLoadingThreadHistoryList={isLoadingThreadHistoryList}
          historySessionEntries={historySessionEntries}
          deletingHistoryKeys={deletingHistoryKeys}
          onCancel={onCloseHistorySessionModal}
          onRetry={onRetryThreadHistoryList}
          onSelectHistorySession={onSelectHistorySession}
          onDeleteHistorySession={onDeleteHistorySession}
        />

        <NewSessionConfigModal
          open={isNewSessionConfigOpen}
          optionCards={newSessionOptionCards}
          summaryItems={newSessionSummaryItems}
          isStepOneDone={isNewSessionStepOneDone}
          isStepTwoDone={isNewSessionStepTwoDone}
          isStepThreeDone={isNewSessionStepThreeDone}
          isStepFourDone={isNewSessionStepFourDone}
          isConfirmDisabled={isNewSessionConfirmDisabled}
          isConfirming={isConfirmingNewSession}
          onCancel={onCancelCreateSession}
          onConfirm={onConfirmCreateSession}
        />
      </div>
    </div>
  );
}

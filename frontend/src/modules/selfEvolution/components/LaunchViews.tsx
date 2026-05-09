import { Modal, Tag, Typography } from "antd";
import { HistoryOutlined, LoadingOutlined } from "@ant-design/icons";
import {
  type SelfEvolutionLaunchOptionCard,
  type SelfEvolutionSummaryItem,
  type SelfEvolutionWorkflowStep,
} from "./types";

const { Paragraph, Text } = Typography;

type LaunchOptionGridProps = {
  optionCards: SelfEvolutionLaunchOptionCard[];
  className?: string;
};

export function LaunchOptionGrid({ optionCards, className = "" }: LaunchOptionGridProps) {
  return (
    <div
      className={`self-evolution-launch-compact-grid ${className}`.trim()}
      role="list"
      aria-label="启动配置选项"
    >
      {optionCards.map((item) => (
        <article
          key={item.key}
          className={`self-evolution-launch-compact-item ${item.toneClassName}${item.isHighlighted ? " is-highlighted" : ""}`}
          role="listitem"
        >
          <div className="self-evolution-launch-compact-meta">
            <span className="self-evolution-launch-card-icon" aria-hidden>
              {item.icon}
            </span>
            <div className="self-evolution-launch-compact-copy">
              <Text className="self-evolution-launch-card-title">{item.title}</Text>
              <Text className="self-evolution-launch-card-current-value">当前：{item.currentValue}</Text>
              <Text className={`self-evolution-launch-compact-desc${item.isDescSingleLine ? " is-single-line" : ""}`}>
                {item.description}
              </Text>
            </div>
          </div>
          {item.control}
        </article>
      ))}
    </div>
  );
}

type LaunchSummaryProps = {
  summaryItems: SelfEvolutionSummaryItem[];
  id?: string;
  ariaLabel: string;
};

export function LaunchSummary({ summaryItems, id, ariaLabel }: LaunchSummaryProps) {
  return (
    <div className="self-evolution-launch-summary" id={id} aria-label={ariaLabel}>
      {summaryItems.map((item) => (
        <div key={item.label} className="self-evolution-launch-summary-pill">
          <Text className="self-evolution-launch-summary-label">{item.label}</Text>
          <Text className="self-evolution-launch-summary-value">{item.value}</Text>
        </div>
      ))}
    </div>
  );
}

type NewSessionConfigModalProps = {
  open: boolean;
  optionCards: SelfEvolutionLaunchOptionCard[];
  summaryItems: SelfEvolutionSummaryItem[];
  isStepOneDone: boolean;
  isStepTwoDone: boolean;
  isStepThreeDone: boolean;
  isStepFourDone: boolean;
  isConfirmDisabled: boolean;
  isConfirming?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
};

export function NewSessionConfigModal({
  open,
  optionCards,
  summaryItems,
  isStepOneDone,
  isStepTwoDone,
  isStepThreeDone,
  isStepFourDone,
  isConfirmDisabled,
  isConfirming = false,
  onCancel,
  onConfirm,
}: NewSessionConfigModalProps) {
  return (
    <Modal
      open={open}
      onCancel={onCancel}
      footer={null}
      width={980}
      centered
      maskClosable={false}
      className="self-evolution-new-session-modal"
      destroyOnClose={false}
      title={null}
    >
      <section className="self-evolution-new-session-shell" aria-label="新会话五步配置">
        <header className="self-evolution-new-session-head">
          <Text className="self-evolution-new-session-kicker">新会话 · 五步重选</Text>
          <Typography.Title level={4} className="self-evolution-new-session-title">
            创建前请重新确认本轮配置
          </Typography.Title>
          <Text className="self-evolution-new-session-subtitle">
            1-4 步为必选项，第 5 步确认后会创建新会话并自动进入 Step 1。
          </Text>
        </header>

        <div className="self-evolution-new-session-step-rail" aria-label="五步流程状态">
          <span className={`self-evolution-new-session-step-chip${isStepOneDone ? " is-done" : ""}`}>
            1. 选择知识库
          </span>
          <span className={`self-evolution-new-session-step-chip${isStepTwoDone ? " is-done" : ""}`}>
            2. 已有评测集
          </span>
          <span className={`self-evolution-new-session-step-chip${isStepThreeDone ? " is-done" : ""}`}>
            3. 补充评测集
          </span>
          <span className={`self-evolution-new-session-step-chip${isStepFourDone ? " is-done" : ""}`}>
            4. 过程干预
          </span>
          <span className="self-evolution-new-session-step-chip is-focus">5. 开始</span>
        </div>

        <LaunchOptionGrid optionCards={optionCards} className="self-evolution-new-session-grid" />

        <footer className="self-evolution-launch-start-bar self-evolution-new-session-start-bar">
          <div className="self-evolution-launch-start-copy">
            <Text className="self-evolution-launch-start-step">5. 开始</Text>
            <Text className="self-evolution-launch-start-title">确认后启动新会话流程</Text>
            <LaunchSummary summaryItems={summaryItems} ariaLabel="新会话配置摘要" />
          </div>

          <div className="self-evolution-new-session-actions">
            <button type="button" className="self-evolution-new-session-cancel" onClick={onCancel}>
              取消
            </button>
            <button
              type="button"
              className="self-evolution-chatlike-start-button"
              onClick={onConfirm}
              disabled={isConfirmDisabled}
            >
              {isConfirming ? "启动中..." : "开始新会话"}
            </button>
          </div>
        </footer>
      </section>
    </Modal>
  );
}

export type SelfEvolutionHomeViewProps = {
  isLoadingThreadHistoryList: boolean;
  workflowSteps: SelfEvolutionWorkflowStep[];
  launchOptionCards: SelfEvolutionLaunchOptionCard[];
  launchSummaryItems: SelfEvolutionSummaryItem[];
  isLaunchConfigValid: boolean;
  isStartingSession: boolean;
  onOpenHistorySessionModal: () => void;
  onStartSession: () => void;
};

export function SelfEvolutionHomeView({
  isLoadingThreadHistoryList,
  workflowSteps,
  launchOptionCards,
  launchSummaryItems,
  isLaunchConfigValid,
  isStartingSession,
  onOpenHistorySessionModal,
  onStartSession,
}: SelfEvolutionHomeViewProps) {
  return (
    <div className="self-evolution-chatlike-page admin-page">
      <header className="self-evolution-chatlike-top">
        <Tag color="blue" className="self-evolution-chatlike-tag">
          单线程会话
        </Tag>
        <div className="self-evolution-chatlike-top-actions">
          <button
            type="button"
            className="self-evolution-chatlike-top-history"
            onClick={onOpenHistorySessionModal}
            aria-label="打开历史会话列表"
          >
            {isLoadingThreadHistoryList ? <LoadingOutlined spin /> : <HistoryOutlined />}
            <span>历史会话</span>
          </button>
        </div>
      </header>

      <section className="self-evolution-welcome-container" aria-label="欢迎与配置">
        <div className="self-evolution-welcome-shell">
          <figure className="self-evolution-welcome-visual">
            <img
              className="self-evolution-welcome-visual-image"
              src="/Lazy.png"
              alt="自进化系统五步流程示意图：生成数据集、评测报告、分析报告、代码优化、A/B 测试"
            />
            <figcaption className="self-evolution-welcome-visual-meta">
              <Text className="self-evolution-welcome-visual-title">自进化执行路径</Text>
              <div className="self-evolution-welcome-visual-badges" role="list" aria-label="流程状态">
                {workflowSteps.map((step) => (
                  <span
                    key={`welcome-badge-${step.renderKey || step.id}`}
                    className={`self-evolution-welcome-visual-badge is-${step.status}`}
                    role="listitem"
                  >
                    {step.title}
                  </span>
                ))}
              </div>
            </figcaption>
          </figure>

          <div className="self-evolution-chatlike-launchpad-content">
            <div className="self-evolution-chatlike-launchpad-header">
              <Text className="self-evolution-chatlike-launchpad-kicker">启动配置</Text>
              <Paragraph className="self-evolution-chatlike-launchpad-subtitle">
                选择知识库、评测集和干预方式后即可开始。
              </Paragraph>
            </div>

            <LaunchOptionGrid optionCards={launchOptionCards} />

            <div className="self-evolution-launch-start-bar" aria-labelledby="self-evolution-launch-start-title">
              <div className="self-evolution-launch-start-copy">
                <Text className="self-evolution-launch-start-step">5. 开始</Text>
                <Text className="self-evolution-launch-start-title" id="self-evolution-launch-start-title">
                  确认后启动本轮优化
                </Text>
                <LaunchSummary
                  summaryItems={launchSummaryItems}
                  id="self-evolution-launch-summary"
                  ariaLabel="当前配置摘要"
                />
              </div>

              <button
                type="button"
                className="self-evolution-chatlike-start-button"
                onClick={onStartSession}
                disabled={!isLaunchConfigValid || isStartingSession}
                aria-describedby="self-evolution-launch-summary"
              >
                {isStartingSession ? "启动中..." : "开始"}
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

import { Typography } from "antd";
import {
  type AnalysisRunSummary,
  type ApplyRunSummary,
  formatAnalysisAgentName,
  formatAnalysisCategory,
  formatAnalysisVerdict,
  formatConfidencePercent,
  formatThreadTime,
  getStepStatusLabel,
} from "../shared";

const { Paragraph, Text } = Typography;

export function AnalysisRuntimeSummary({ summary }: { summary?: AnalysisRunSummary }) {
  if (!summary) {
    return null;
  }

  const statItems = [
    { label: "调查项", value: String(summary.hypothesisCount) },
    { label: "子代理", value: String(summary.agentCount) },
    { label: "已回收结论", value: String(summary.completedAgentCount) },
    {
      label: "编排轮次",
      value: summary.iterationCount ? `${summary.iterationCount} 轮` : "进行中",
    },
  ];

  return (
    <section className="self-evolution-execution-summary" aria-label="分析执行概览">
      <div className="self-evolution-execution-summary-head">
        <Text>分析执行概览</Text>
        <span className={`self-evolution-inline-status is-${summary.status}`}>
          {getStepStatusLabel(summary.status)}
        </span>
      </div>

      <div className="self-evolution-execution-stat-grid" role="list" aria-label="分析执行统计">
        {statItems.map((item) => (
          <div key={item.label} className="self-evolution-execution-stat" role="listitem">
            <span className="self-evolution-execution-stat-label">{item.label}</span>
            <strong className="self-evolution-execution-stat-value">{item.value}</strong>
          </div>
        ))}
      </div>

      {summary.timeline.length > 0 && (
        <div className="self-evolution-execution-section">
          <Text className="self-evolution-execution-section-title">关键过程</Text>
          <div className="self-evolution-execution-timeline">
            {summary.timeline.slice(-5).map((item) => (
              <div key={item.key} className="self-evolution-execution-timeline-item">
                <div className="self-evolution-execution-timeline-meta">
                  <strong>{item.title}</strong>
                  {item.time && <span>{formatThreadTime(item.time)}</span>}
                </div>
                <p>{item.detail}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {summary.hypotheses.length > 0 && (
        <div className="self-evolution-execution-section">
          <Text className="self-evolution-execution-section-title">调查结论</Text>
          <div className="self-evolution-execution-list">
            {summary.hypotheses.slice(0, 4).map((item) => (
              <div key={item.id} className="self-evolution-execution-list-item">
                <div className="self-evolution-execution-list-head">
                  <div className="self-evolution-execution-list-title">
                    <strong>{item.id}</strong>
                    <span>{formatAnalysisCategory(item.category)}</span>
                  </div>
                  <div className="self-evolution-execution-list-tags">
                    <span className={`self-evolution-inline-tag is-${item.verdict || "pending"}`}>
                      {formatAnalysisVerdict(item.verdict)}
                    </span>
                    {formatConfidencePercent(item.confidence) && (
                      <span className="self-evolution-inline-tag is-neutral">
                        {formatConfidencePercent(item.confidence)}
                      </span>
                    )}
                  </div>
                </div>
                <p>{item.refinedClaim || item.claim}</p>
                {item.suggestedAction && (
                  <span className="self-evolution-execution-list-note">{`建议动作：${item.suggestedAction}`}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {summary.agents.length > 0 && (
        <div className="self-evolution-execution-section">
          <Text className="self-evolution-execution-section-title">子代理进展</Text>
          <div className="self-evolution-execution-agent-list">
            {summary.agents.slice(0, 5).map((item) => (
              <div key={item.agent} className="self-evolution-execution-agent-row">
                <div className="self-evolution-execution-agent-main">
                  <strong>{formatAnalysisAgentName(item.agent)}</strong>
                  <span>{`工具 ${item.toolCallCount} 次${item.rounds ? `，调查 ${item.rounds} 轮` : ""}`}</span>
                </div>
                <div className="self-evolution-execution-agent-side">
                  {item.hypothesisId && <span>{item.hypothesisId}</span>}
                  <span className={`self-evolution-inline-tag is-${item.verdict || "pending"}`}>
                    {formatAnalysisVerdict(item.verdict)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {summary.crossStepNarrative && (
        <Paragraph className="self-evolution-execution-summary-note">
          {summary.crossStepNarrative}
        </Paragraph>
      )}
    </section>
  );
}

export function ApplyRuntimeSummary({ summary }: { summary?: ApplyRunSummary }) {
  if (!summary) {
    return null;
  }

  const statItems = [
    { label: "优化轮次", value: summary.roundCount ? `${summary.roundCount} 轮` : "准备中" },
    { label: "改动文件", value: `${summary.changedFileCount} 个` },
    { label: "测试状态", value: summary.testStatusText || "待确认" },
  ];

  return (
    <section className="self-evolution-execution-summary" aria-label="代码优化执行概览">
      <div className="self-evolution-execution-summary-head">
        <Text>代码优化概览</Text>
        <span className={`self-evolution-inline-status is-${summary.status}`}>
          {getStepStatusLabel(summary.status)}
        </span>
      </div>

      <div className="self-evolution-execution-stat-grid" role="list" aria-label="代码优化统计">
        {statItems.map((item) => (
          <div key={item.label} className="self-evolution-execution-stat" role="listitem">
            <span className="self-evolution-execution-stat-label">{item.label}</span>
            <strong className="self-evolution-execution-stat-value">{item.value}</strong>
          </div>
        ))}
      </div>

      {summary.timeline.length > 0 && (
        <div className="self-evolution-execution-section">
          <Text className="self-evolution-execution-section-title">执行过程</Text>
          <div className="self-evolution-execution-timeline">
            {summary.timeline.map((item) => (
              <div key={item.key} className="self-evolution-execution-timeline-item">
                <div className="self-evolution-execution-timeline-meta">
                  <strong>{item.title}</strong>
                  {item.time && <span>{formatThreadTime(item.time)}</span>}
                </div>
                <p>{item.detail}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {summary.changedFiles.length > 0 && (
        <div className="self-evolution-execution-section">
          <Text className="self-evolution-execution-section-title">涉及文件</Text>
          <div className="self-evolution-file-chip-list" role="list" aria-label="改动文件列表">
            {summary.changedFiles.map((file) => (
              <span key={file} className="self-evolution-file-chip" role="listitem">
                {file}
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

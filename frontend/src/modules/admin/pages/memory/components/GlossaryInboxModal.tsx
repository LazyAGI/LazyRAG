import { Alert, Button, Checkbox, Empty, Modal, Space, Spin, Tag } from "antd";
import type { TFunction } from "i18next";
import { useEffect, useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import type {
  GlossaryChangeProposal,
  GlossaryConflictResolution,
  GlossarySource,
} from "../shared";

interface GlossaryInboxModalProps {
  t: TFunction;
  glossaryInboxOpen: boolean;
  setGlossaryInboxOpen: (open: boolean) => void;
  rejectSelectedGlossaryProposals: () => void;
  glossaryChangeProposals: GlossaryChangeProposal[];
  glossaryInboxLoading: boolean;
  glossaryInboxError: string;
  glossaryInboxSubmitting: "" | "accept" | "reject";
  refreshGlossaryConflicts: (options?: { showErrorToast?: boolean; silent?: boolean }) => void;
  isAllGlossaryProposalsSelected: boolean;
  isPartialGlossaryProposalSelected: boolean;
  setSelectedGlossaryProposalIds: Dispatch<SetStateAction<string[]>>;
  glossaryProposalIds: string[];
  selectedGlossaryProposalIds: string[];
  glossarySourceColorMap: Record<GlossarySource, string>;
  glossarySourceLabelMap: Record<GlossarySource, string>;
  rejectGlossaryProposals: (proposals: GlossaryChangeProposal[]) => void;
  applyGlossaryProposals: (
    proposals: GlossaryChangeProposal[],
    resolutions?: Record<string, GlossaryConflictResolution>,
  ) => void;
}

const getDefaultResolution = (proposal: GlossaryChangeProposal): GlossaryConflictResolution => {
  const targetGroupIds = proposal.backendConflictGroupIds || [];
  return {
    mode: targetGroupIds.length ? "separate" : "create",
    selectedGroupIds: targetGroupIds,
    newGroupTerm: proposal.after.term,
  };
};

export default function GlossaryInboxModal(props: GlossaryInboxModalProps) {
  const {
    t,
    glossaryInboxOpen,
    setGlossaryInboxOpen,
    rejectSelectedGlossaryProposals,
    glossaryChangeProposals,
    glossaryInboxLoading,
    glossaryInboxError,
    glossaryInboxSubmitting,
    refreshGlossaryConflicts,
    isAllGlossaryProposalsSelected,
    isPartialGlossaryProposalSelected,
    setSelectedGlossaryProposalIds,
    glossaryProposalIds,
    selectedGlossaryProposalIds,
    glossarySourceColorMap,
    glossarySourceLabelMap,
    rejectGlossaryProposals,
    applyGlossaryProposals,
  } = props;
  const [resolutionMap, setResolutionMap] = useState<
    Record<string, GlossaryConflictResolution>
  >({});

  useEffect(() => {
    setResolutionMap((previous) => {
      const proposalIdSet = new Set(glossaryChangeProposals.map((proposal) => proposal.id));
      const next: Record<string, GlossaryConflictResolution> = {};

      glossaryChangeProposals.forEach((proposal) => {
        next[proposal.id] = previous[proposal.id] || getDefaultResolution(proposal);
      });

      Object.keys(previous).forEach((proposalId) => {
        if (!proposalIdSet.has(proposalId)) {
          delete next[proposalId];
        }
      });

      return next;
    });
  }, [glossaryChangeProposals]);

  const hasSelection = selectedGlossaryProposalIds.length > 0;
  const isSubmitting = Boolean(glossaryInboxSubmitting);
  const selectedGlossaryProposals = useMemo(
    () =>
      glossaryChangeProposals.filter((proposal) =>
        selectedGlossaryProposalIds.includes(proposal.id),
      ),
    [glossaryChangeProposals, selectedGlossaryProposalIds],
  );
  const buildResolutionWithMode = (
    proposal: GlossaryChangeProposal,
    mode: GlossaryConflictResolution["mode"],
  ): GlossaryConflictResolution => ({
    ...(resolutionMap[proposal.id] || getDefaultResolution(proposal)),
    mode,
  });
  const isResolutionValidForMode = (
    proposal: GlossaryChangeProposal,
    mode: GlossaryConflictResolution["mode"],
  ) => {
    const resolution = buildResolutionWithMode(proposal, mode);

    if (mode === "create") {
      return Boolean(resolution.newGroupTerm.trim());
    }

    if (mode === "merge") {
      return resolution.selectedGroupIds.length >= 2;
    }

    return resolution.selectedGroupIds.length > 0;
  };
  const buildSelectedResolutionMapWithMode = (
    mode: GlossaryConflictResolution["mode"],
  ): Record<string, GlossaryConflictResolution> =>
    selectedGlossaryProposals.reduce<Record<string, GlossaryConflictResolution>>(
      (result, proposal) => {
        result[proposal.id] = buildResolutionWithMode(proposal, mode);
        return result;
      },
      {},
    );
  const canApplySelectedWithMode = (mode: GlossaryConflictResolution["mode"]) =>
    selectedGlossaryProposals.length > 0 &&
    selectedGlossaryProposals.every((proposal) =>
      isResolutionValidForMode(proposal, mode),
    );
  const applyProposalWithMode = (
    proposal: GlossaryChangeProposal,
    mode: GlossaryConflictResolution["mode"],
  ) => {
    applyGlossaryProposals([proposal], {
      [proposal.id]: buildResolutionWithMode(proposal, mode),
    });
  };
  const updateResolution = (
    proposal: GlossaryChangeProposal,
    patch: Partial<GlossaryConflictResolution>,
  ) => {
    setResolutionMap((previous) => {
      const current = previous[proposal.id] || getDefaultResolution(proposal);
      return {
        ...previous,
        [proposal.id]: {
          ...current,
          ...patch,
        },
      };
    });
  };

  return (
    <Modal
      open={glossaryInboxOpen}
      title={t("admin.memoryGlossaryInboxTitle")}
      onCancel={() => setGlossaryInboxOpen(false)}
      width={960}
      footer={[
        <Button key="close" disabled={isSubmitting} onClick={() => setGlossaryInboxOpen(false)}>
          {t("common.close")}
        </Button>,
        <Button
          key="reject"
          disabled={!hasSelection || glossaryInboxLoading || isSubmitting}
          loading={glossaryInboxSubmitting === "reject"}
          onClick={rejectSelectedGlossaryProposals}
        >
          {t("admin.memoryGlossaryInboxReject")}
        </Button>,
        <Button
          key="separate"
          type="primary"
          disabled={!hasSelection || !canApplySelectedWithMode("separate") || glossaryInboxLoading || isSubmitting}
          loading={glossaryInboxSubmitting === "accept"}
          onClick={() =>
            applyGlossaryProposals(
              selectedGlossaryProposals,
              buildSelectedResolutionMapWithMode("separate"),
            )
          }
        >
          {t("admin.memoryGlossaryInboxWriteSeparately")}
        </Button>,
        <Button
          key="create"
          disabled={!hasSelection || !canApplySelectedWithMode("create") || glossaryInboxLoading || isSubmitting}
          loading={glossaryInboxSubmitting === "accept"}
          onClick={() =>
            applyGlossaryProposals(
              selectedGlossaryProposals,
              buildSelectedResolutionMapWithMode("create"),
            )
          }
        >
          {t("admin.memoryGlossaryInboxCreateAndWrite")}
        </Button>,
      ]}
    >
      {glossaryInboxError ? (
        <Alert
          type="error"
          showIcon
          className="memory-skill-share-alert"
          message={glossaryInboxError}
          action={
            <Button
              size="small"
              disabled={glossaryInboxLoading || isSubmitting}
              onClick={() => refreshGlossaryConflicts({ showErrorToast: true })}
            >
              {t("common.retry")}
            </Button>
          }
        />
      ) : null}

      {glossaryInboxLoading ? (
        <div className="memory-glossary-inbox-loading">
          <Spin />
          <span>{t("common.loading")}</span>
        </div>
      ) : glossaryChangeProposals.length ? (
        <div className="memory-glossary-inbox">
          <div className="memory-glossary-inbox-toolbar">
            <Checkbox
              checked={isAllGlossaryProposalsSelected}
              indeterminate={isPartialGlossaryProposalSelected}
              disabled={isSubmitting}
              onChange={(event) =>
                setSelectedGlossaryProposalIds(
                  event.target.checked ? [...glossaryProposalIds] : [],
                )
              }
            >
              {t("admin.memoryGlossaryInboxSelectAll")}
            </Checkbox>
            <span>
              {t("admin.memoryGlossaryInboxStats", {
                selected: selectedGlossaryProposalIds.length,
                total: glossaryChangeProposals.length,
              })}
            </span>
          </div>
          <div className="memory-glossary-inbox-list">
            {glossaryChangeProposals.map((proposal) => {
              const checked = selectedGlossaryProposalIds.includes(proposal.id);
              const isMergeProposal = Boolean(proposal.mergeFrom?.length);
              const targetGroups = proposal.backendConflictGroups || [];
              const resolution = resolutionMap[proposal.id] || getDefaultResolution(proposal);
              const hasTargetGroups = targetGroups.length > 0;
              const proposalTypeText = isMergeProposal
                ? t("admin.memoryGlossaryInboxTypeMerge")
                : proposal.before
                  ? t("admin.memoryGlossaryInboxTypeUpdate")
                  : t("admin.memoryGlossaryInboxTypeAdd");

              return (
                <div key={proposal.id} className="memory-glossary-inbox-card">
                  <div className="memory-glossary-inbox-card-head">
                    <Checkbox
                      checked={checked}
                      disabled={isSubmitting}
                      onChange={(event) =>
                        setSelectedGlossaryProposalIds((previous: string[]) =>
                          event.target.checked
                            ? [...previous, proposal.id]
                            : previous.filter((id) => id !== proposal.id),
                        )
                      }
                    >
                      {proposal.after.term}
                    </Checkbox>
                    <Space size={8}>
                      <Tag color="blue">{proposalTypeText}</Tag>
                      <Tag color={glossarySourceColorMap[proposal.after.source]}>
                        {glossarySourceLabelMap[proposal.after.source]}
                      </Tag>
                    </Space>
                  </div>
                  <div className="memory-glossary-inbox-card-body">
                    <div className="memory-glossary-inbox-card-line">
                      <strong>{t("admin.memoryGlossaryInboxReason")}</strong>
                      <span>{proposal.reason}</span>
                    </div>
                    <div className="memory-glossary-inbox-card-line">
                      <strong>{t("admin.memoryGlossaryAliases")}</strong>
                      <div className="memory-tag-group memory-tag-group-scroll">
                        {proposal.after.aliases.length ? (
                          proposal.after.aliases.map((alias: string) => (
                            <Tag key={`${proposal.id}-${alias}`}>{alias}</Tag>
                          ))
                        ) : (
                          <span className="memory-content-preview">-</span>
                        )}
                      </div>
                    </div>
                    {hasTargetGroups ? (
                      <div className="memory-glossary-inbox-card-line">
                        <strong>{t("admin.memoryGlossaryInboxTargetGroups")}</strong>
                        <div className="memory-glossary-target-panel">
                          <Checkbox.Group
                            value={resolution.selectedGroupIds}
                            disabled={isSubmitting}
                            onChange={(values) =>
                              updateResolution(proposal, {
                                selectedGroupIds: values.map((value) => String(value)),
                              })
                            }
                          >
                            <div className="memory-glossary-target-grid">
                              {targetGroups.map((group) => {
                                const isSelected = resolution.selectedGroupIds.includes(group.id);
                                return (
                                  <label
                                    key={`${proposal.id}-${group.id}`}
                                    className={`memory-glossary-target-card ${
                                      isSelected ? "is-selected" : ""
                                    }`}
                                  >
                                    <Checkbox value={group.id} disabled={isSubmitting} />
                                    <span className="memory-glossary-target-main">
                                      <strong>{group.term || group.id}</strong>
                                      <span className="memory-glossary-target-id">
                                        {group.id}
                                      </span>
                                      <span className="memory-tag-group memory-tag-group-scroll">
                                        {group.aliases.length ? (
                                          group.aliases.map((alias) => (
                                            <Tag key={`${proposal.id}-${group.id}-${alias}`}>
                                              {alias}
                                            </Tag>
                                          ))
                                        ) : (
                                          <span className="memory-content-preview">-</span>
                                        )}
                                      </span>
                                    </span>
                                  </label>
                                );
                              })}
                            </div>
                          </Checkbox.Group>
                        </div>
                      </div>
                    ) : null}
                  </div>
                  <div className="memory-glossary-inbox-card-actions">
                    <Button
                      size="small"
                      disabled={isSubmitting}
                      loading={
                        glossaryInboxSubmitting === "reject" &&
                        selectedGlossaryProposalIds.includes(proposal.id)
                      }
                      onClick={() => rejectGlossaryProposals([proposal])}
                    >
                      {t("admin.memoryGlossaryInboxReject")}
                    </Button>
                    <Button
                      size="small"
                      type="primary"
                      disabled={isSubmitting || !isResolutionValidForMode(proposal, "separate")}
                      loading={
                        glossaryInboxSubmitting === "accept" &&
                        selectedGlossaryProposalIds.includes(proposal.id)
                      }
                      onClick={() => applyProposalWithMode(proposal, "separate")}
                    >
                      {t("admin.memoryGlossaryInboxWriteSeparately")}
                    </Button>
                    <Button
                      size="small"
                      disabled={isSubmitting || !isResolutionValidForMode(proposal, "merge")}
                      loading={
                        glossaryInboxSubmitting === "accept" &&
                        selectedGlossaryProposalIds.includes(proposal.id)
                      }
                      onClick={() => applyProposalWithMode(proposal, "merge")}
                    >
                      {t("admin.memoryGlossaryInboxMergeAndWrite")}
                    </Button>
                    <Button
                      size="small"
                      disabled={isSubmitting || !isResolutionValidForMode(proposal, "create")}
                      loading={
                        glossaryInboxSubmitting === "accept" &&
                        selectedGlossaryProposalIds.includes(proposal.id)
                      }
                      onClick={() => applyProposalWithMode(proposal, "create")}
                    >
                      {t("admin.memoryGlossaryInboxCreateAndWrite")}
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t("admin.memoryGlossaryInboxEmpty")}
        />
      )}
    </Modal>
  );
}

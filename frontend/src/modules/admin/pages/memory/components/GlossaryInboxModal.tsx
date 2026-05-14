import {
  Alert,
  Button,
  Checkbox,
  Dropdown,
  Empty,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Spin,
  Steps,
  Tag,
} from "antd";
import type { TFunction } from "i18next";
import { useEffect, useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import type {
  GlossaryAsset,
  GlossaryChangeProposal,
  GlossaryConflictResolution,
  GlossaryConflictResolveMode,
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

interface PendingAction {
  proposal: GlossaryChangeProposal;
  mode: GlossaryConflictResolveMode;
}

const getDefaultResolution = (proposal: GlossaryChangeProposal): GlossaryConflictResolution => {
  const targetGroupIds = proposal.backendConflictGroupIds || [];
  return {
    mode: targetGroupIds.length ? "separate" : "create",
    selectedGroupIds: targetGroupIds,
    newGroupTerm: proposal.after.term,
    newGroupAliases: proposal.after.aliases.length ? proposal.after.aliases : [proposal.after.term],
    newGroupContent: proposal.after.content,
  };
};

const getUniqueTexts = (items: string[]) =>
  [...new Set(items.map((item) => item.trim()).filter(Boolean))];

const getConflictWord = (proposal: GlossaryChangeProposal) =>
  proposal.backendConflictWord || proposal.after.term;

const buildCreateResolution = (
  proposal: GlossaryChangeProposal,
  resolution: GlossaryConflictResolution,
): GlossaryConflictResolution => {
  const conflictWord = getConflictWord(proposal);
  const aliases = getUniqueTexts([
    ...(resolution.newGroupAliases?.length
      ? resolution.newGroupAliases
      : proposal.after.aliases),
    conflictWord,
  ]);

  return {
    ...resolution,
    mode: "create",
    selectedGroupIds: [],
    newGroupTerm: resolution.newGroupTerm.trim(),
    newGroupAliases: aliases,
    newGroupContent: (resolution.newGroupContent ?? proposal.after.content).trim(),
  };
};

const buildMergedDraft = (
  proposal: GlossaryChangeProposal,
  selectedGroups: GlossaryAsset[],
  resolution: GlossaryConflictResolution,
) => {
  const conflictWord = getConflictWord(proposal);
  const fallbackTerm = selectedGroups[0]?.term || proposal.after.term;
  const fallbackAliases = getUniqueTexts([
    conflictWord,
    proposal.after.term,
    ...proposal.after.aliases,
    ...selectedGroups.flatMap((group) => [group.term, ...group.aliases]),
  ]).filter((item) => item !== fallbackTerm);
  const fallbackContent = getUniqueTexts([
    ...selectedGroups.map((group) => group.content),
    proposal.after.content,
  ]).join("\n\n");

  return {
    term: (resolution.mergedGroupTerm || fallbackTerm).trim(),
    aliases: resolution.mergedGroupAliases?.length
      ? resolution.mergedGroupAliases
      : fallbackAliases,
    content: (resolution.mergedGroupContent ?? fallbackContent).trim(),
  };
};

const GlossaryGroupCards = ({
  groups,
  selectedGroupIds,
  disabled,
  onChange,
  t,
}: {
  groups: GlossaryAsset[];
  selectedGroupIds: string[];
  disabled: boolean;
  onChange: (groupIds: string[]) => void;
  t: TFunction;
}) => (
  <div className="memory-glossary-target-panel">
    <Checkbox.Group
      value={selectedGroupIds}
      disabled={disabled}
      onChange={(values) => onChange(values.map((value) => String(value)))}
    >
      <div className="memory-glossary-target-grid">
        {groups.map((group) => {
          const isSelected = selectedGroupIds.includes(group.id);
          return (
            <label
              key={group.id}
              className={`memory-glossary-target-card ${isSelected ? "is-selected" : ""}`}
            >
              <Checkbox value={group.id} disabled={disabled} />
              <span className="memory-glossary-target-main">
                <strong>{group.term || t("admin.memoryGlossaryGroupUnassigned")}</strong>
                <span className="memory-glossary-target-id">{group.id}</span>
                <span className="memory-tag-group memory-tag-group-scroll">
                  {group.aliases.length ? (
                    group.aliases.map((alias) => <Tag key={`${group.id}-${alias}`}>{alias}</Tag>)
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
);

const GlossaryGroupPreviewCards = ({
  groups,
  t,
}: {
  groups: GlossaryAsset[];
  t: TFunction;
}) => (
  <div className="memory-glossary-target-preview-grid">
    {groups.map((group) => (
      <div key={group.id} className="memory-glossary-target-preview-card">
        <span className="memory-glossary-target-preview-main">
          <strong>{group.term || t("admin.memoryGlossaryGroupUnassigned")}</strong>
          <span className="memory-tag-group">
            {group.aliases.length ? (
              group.aliases.map((alias) => <Tag key={`${group.id}-${alias}`}>{alias}</Tag>)
            ) : (
              <span className="memory-content-preview">-</span>
            )}
          </span>
        </span>
      </div>
    ))}
  </div>
);

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
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);
  const [mergeStep, setMergeStep] = useState<"select" | "edit">("select");

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

  useEffect(() => {
    if (
      pendingAction &&
      !glossaryChangeProposals.some((proposal) => proposal.id === pendingAction.proposal.id)
    ) {
      setPendingAction(null);
      setMergeStep("select");
    }
  }, [glossaryChangeProposals, pendingAction]);

  const hasSelection = selectedGlossaryProposalIds.length > 0;
  const isSubmitting = Boolean(glossaryInboxSubmitting);
  const activeResolution = pendingAction
    ? resolutionMap[pendingAction.proposal.id] || getDefaultResolution(pendingAction.proposal)
    : null;
  const selectedActionGroups = useMemo(
    () => pendingAction?.proposal.backendConflictGroups || [],
    [pendingAction],
  );
  const selectedMergeGroups = useMemo(
    () =>
      activeResolution
        ? selectedActionGroups.filter((group) =>
            activeResolution.selectedGroupIds.includes(group.id),
          )
        : [],
    [activeResolution, selectedActionGroups],
  );
  const mergedDraft =
    pendingAction?.mode === "merge" && activeResolution
      ? buildMergedDraft(pendingAction.proposal, selectedMergeGroups, activeResolution)
      : null;
  const isGroupAction = pendingAction?.mode === "separate" || pendingAction?.mode === "merge";
  const isCreateAction = pendingAction?.mode === "create";
  const isActiveActionValid = (() => {
    if (!pendingAction || !activeResolution) {
      return false;
    }

    if (pendingAction.mode === "create") {
      return Boolean(activeResolution.newGroupTerm.trim());
    }

    if (pendingAction.mode === "merge") {
      return activeResolution.selectedGroupIds.length >= 2;
    }

    return activeResolution.selectedGroupIds.length > 0;
  })();

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

  const openAction = (
    proposal: GlossaryChangeProposal,
    mode: GlossaryConflictResolveMode,
  ) => {
    updateResolution(proposal, { mode });
    setMergeStep("select");
    setPendingAction({ proposal, mode });
  };

  const submitPendingAction = () => {
    if (!pendingAction || !activeResolution) {
      return;
    }

    if (pendingAction.mode === "merge" && mergeStep === "select") {
      setMergeStep("edit");
      return;
    }

    if (pendingAction.mode === "merge" && !mergedDraft?.term) {
      return;
    }

    const resolution =
      pendingAction.mode === "create"
        ? buildCreateResolution(pendingAction.proposal, activeResolution)
        : pendingAction.mode === "merge" && mergedDraft
          ? {
              ...activeResolution,
              mode: pendingAction.mode,
              mergedGroupTerm: mergedDraft.term,
              mergedGroupAliases: mergedDraft.aliases,
              mergedGroupContent: mergedDraft.content,
            }
        : {
            ...activeResolution,
            mode: pendingAction.mode,
          };

    applyGlossaryProposals([pendingAction.proposal], {
      [pendingAction.proposal.id]: resolution,
    });
  };

  const getActionTitle = () => {
    if (!pendingAction) {
      return "";
    }

    if (pendingAction.mode === "merge") {
      return t("admin.memoryGlossaryInboxMergeAndWrite");
    }

    if (pendingAction.mode === "create") {
      return t("admin.memoryGlossaryInboxCreateAndWrite");
    }

    return t("admin.memoryGlossaryInboxWriteSeparately");
  };

  return (
    <>
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
                const proposalTypeText = isMergeProposal
                  ? t("admin.memoryGlossaryInboxTypeMerge")
                  : proposal.before
                    ? t("admin.memoryGlossaryInboxTypeUpdate")
                    : t("admin.memoryGlossaryInboxTypeAdd");
                const actionMenuItems = [
                  {
                    key: "reject",
                    danger: true,
                    label: (
                      <span className="memory-glossary-action-menu-item">
                        <strong>{t("admin.memoryGlossaryInboxActionRejectTitle")}</strong>
                        <span>{t("admin.memoryGlossaryInboxActionRejectDesc")}</span>
                      </span>
                    ),
                  },
                  {
                    key: "separate",
                    disabled: !targetGroups.length,
                    label: (
                      <span className="memory-glossary-action-menu-item">
                        <strong>{t("admin.memoryGlossaryInboxActionAddTitle")}</strong>
                        <span>{t("admin.memoryGlossaryInboxActionAddDesc")}</span>
                      </span>
                    ),
                  },
                  {
                    key: "merge",
                    disabled: targetGroups.length < 2,
                    label: (
                      <span className="memory-glossary-action-menu-item">
                        <strong>{t("admin.memoryGlossaryInboxActionMergeTitle")}</strong>
                        <span>{t("admin.memoryGlossaryInboxActionMergeDesc")}</span>
                      </span>
                    ),
                  },
                  {
                    key: "create",
                    label: (
                      <span className="memory-glossary-action-menu-item">
                        <strong>{t("admin.memoryGlossaryInboxActionCreateTitle")}</strong>
                        <span>{t("admin.memoryGlossaryInboxActionCreateDesc")}</span>
                      </span>
                    ),
                  },
                ];

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
                      {targetGroups.length ? (
                        <div className="memory-glossary-inbox-card-line">
                          <strong>{t("admin.memoryGlossaryInboxTargetGroups")}</strong>
                          <GlossaryGroupPreviewCards groups={targetGroups} t={t} />
                        </div>
                      ) : null}
                    </div>
                    <div className="memory-glossary-inbox-card-actions">
                      <Dropdown
                        trigger={["click"]}
                        disabled={isSubmitting}
                        menu={{
                          items: actionMenuItems,
                          onClick: ({ key }) => {
                            if (key === "reject") {
                              rejectGlossaryProposals([proposal]);
                              return;
                            }
                            if (key === "separate") {
                              openAction(proposal, "separate");
                              return;
                            }
                            if (key === "merge") {
                              openAction(proposal, "merge");
                              return;
                            }
                            openAction(proposal, "create");
                          },
                        }}
                      >
                        <Button
                          className="memory-glossary-action-trigger"
                          loading={
                            glossaryInboxSubmitting === "reject" &&
                            selectedGlossaryProposalIds.includes(proposal.id)
                          }
                        >
                          {t("admin.memoryGlossaryInboxActionTrigger")}
                        </Button>
                      </Dropdown>
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

      <Modal
        open={Boolean(pendingAction)}
        title={getActionTitle()}
        width={720}
        destroyOnClose
        onCancel={() => {
          setPendingAction(null);
          setMergeStep("select");
        }}
        okText={
          pendingAction?.mode === "merge" && mergeStep === "select"
            ? t("admin.dataSourceWizardNext")
            : t("common.confirm")
        }
        cancelText={t("common.cancel")}
        confirmLoading={glossaryInboxSubmitting === "accept"}
        okButtonProps={{
          disabled:
            isSubmitting ||
            !isActiveActionValid ||
            (pendingAction?.mode === "merge" && mergeStep === "edit" && !mergedDraft?.term),
        }}
        cancelButtonProps={{ disabled: isSubmitting }}
        onOk={submitPendingAction}
      >
        {pendingAction && activeResolution ? (
          <div className="memory-glossary-resolution">
            {pendingAction.mode === "merge" ? (
              <Steps
                size="small"
                current={mergeStep === "select" ? 0 : 1}
                items={[
                  { title: t("admin.memoryGlossaryInboxTargetGroups") },
                  { title: t("admin.memoryGlossaryInboxMergeResult") },
                ]}
              />
            ) : null}
            <div className="memory-glossary-resolution-word">
              <span>{t("admin.memoryGlossaryTerm")}</span>
              <strong>{getConflictWord(pendingAction.proposal)}</strong>
            </div>

            {isGroupAction && (pendingAction.mode !== "merge" || mergeStep === "select") ? (
              <GlossaryGroupCards
                groups={selectedActionGroups}
                selectedGroupIds={activeResolution.selectedGroupIds}
                disabled={isSubmitting}
                t={t}
                onChange={(selectedGroupIds) =>
                  updateResolution(pendingAction.proposal, { selectedGroupIds })
                }
              />
            ) : null}

            {pendingAction.mode === "merge" && mergeStep === "edit" && mergedDraft ? (
              <Form layout="vertical" className="memory-glossary-create-form">
                <Alert
                  type="info"
                  showIcon
                  message={t("admin.memoryGlossaryBatchMergeDraftHint", {
                    count: Math.max(activeResolution.selectedGroupIds.length - 1, 0),
                  })}
                />
                <Form.Item
                  label={t("admin.memoryGlossaryTerm")}
                  required
                  validateStatus={!mergedDraft.term ? "error" : ""}
                  help={!mergedDraft.term ? t("admin.memoryGlossaryGroupRequired") : undefined}
                >
                  <Input
                    value={mergedDraft.term}
                    disabled={isSubmitting}
                    maxLength={50}
                    showCount
                    onChange={(event) =>
                      updateResolution(pendingAction.proposal, {
                        mergedGroupTerm: event.target.value,
                      })
                    }
                  />
                </Form.Item>
                <Form.Item label={t("admin.memoryGlossaryAliases")}>
                  <Select
                    mode="tags"
                    value={mergedDraft.aliases}
                    disabled={isSubmitting}
                    placeholder={t("admin.memoryGlossaryAliasesPlaceholder")}
                    onChange={(values) =>
                      updateResolution(pendingAction.proposal, {
                        mergedGroupAliases: getUniqueTexts(values),
                      })
                    }
                  />
                </Form.Item>
                <Form.Item label={t("admin.memoryContent")}>
                  <Input.TextArea
                    rows={10}
                    maxLength={300}
                    showCount
                    value={mergedDraft.content}
                    disabled={isSubmitting}
                    onChange={(event) =>
                      updateResolution(pendingAction.proposal, {
                        mergedGroupContent: event.target.value,
                      })
                    }
                  />
                </Form.Item>
              </Form>
            ) : null}

            {isCreateAction ? (
              <Form layout="vertical" className="memory-glossary-create-form">
                <Form.Item
                  label={t("admin.memoryGlossaryGroup")}
                  required
                  validateStatus={!activeResolution.newGroupTerm.trim() ? "error" : ""}
                  help={
                    !activeResolution.newGroupTerm.trim()
                      ? t("admin.memoryGlossaryInboxNewGroupRequired")
                      : undefined
                  }
                >
                  <Input
                    value={activeResolution.newGroupTerm}
                    disabled={isSubmitting}
                    placeholder={t("admin.memoryGlossaryInboxNewGroupPlaceholder")}
                    onChange={(event) =>
                      updateResolution(pendingAction.proposal, {
                        newGroupTerm: event.target.value,
                      })
                    }
                  />
                </Form.Item>
                <Form.Item label={t("admin.memoryGlossaryAliases")}>
                  <Input.TextArea
                    autoSize={{ minRows: 2, maxRows: 4 }}
                    value={(activeResolution.newGroupAliases || []).join("\n")}
                    disabled={isSubmitting}
                    onChange={(event) =>
                      updateResolution(pendingAction.proposal, {
                        newGroupAliases: getUniqueTexts(event.target.value.split(/\n|,/)),
                      })
                    }
                  />
                </Form.Item>
                <Form.Item label={t("admin.memoryContent")}>
                  <Input.TextArea
                    autoSize={{ minRows: 3, maxRows: 6 }}
                    value={activeResolution.newGroupContent ?? pendingAction.proposal.after.content}
                    disabled={isSubmitting}
                    onChange={(event) =>
                      updateResolution(pendingAction.proposal, {
                        newGroupContent: event.target.value,
                      })
                    }
                  />
                </Form.Item>
              </Form>
            ) : null}
          </div>
        ) : null}
      </Modal>
    </>
  );
}

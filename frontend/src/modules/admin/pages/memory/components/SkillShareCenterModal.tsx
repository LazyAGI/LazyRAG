import {
  Alert,
  Button,
  Empty,
  Modal,
  Popconfirm,
  Segmented,
  Skeleton,
  Space,
  Tag,
} from "antd";
import type { SkillShareStatus } from "../skillApi";

interface SkillShareCenterModalProps {
  t: any;
  skillShareCenterOpen: boolean;
  closeSkillShareCenter: () => void;
  skillShareCenterTab: "incoming" | "outgoing";
  setSkillShareCenterTab: (value: "incoming" | "outgoing") => void;
  incomingPendingCount: number;
  outgoingSkillShares: any[];
  skillShareCenterLoading: boolean;
  refreshSkillShareCenter: (options?: { showErrorToast?: boolean }) => Promise<void>;
  skillShareCenterError: string;
  currentSkillShareList: any[];
  skillShareActionState: Record<string, string | undefined>;
  getSkillShareStatusMeta: (status: SkillShareStatus) => { color: string; text: string };
  formatDateTime: (value?: string) => string;
  previewSkillShare: (share: any) => Promise<void>;
  rejectIncomingSkillShare: (share: any) => Promise<void>;
  acceptIncomingSkillShare: (share: any) => Promise<void>;
  isSkillShareActionable: (status: SkillShareStatus) => boolean;
}

export default function SkillShareCenterModal(props: SkillShareCenterModalProps) {
  const {
    t,
    skillShareCenterOpen,
    closeSkillShareCenter,
    skillShareCenterTab,
    setSkillShareCenterTab,
    incomingPendingCount,
    outgoingSkillShares,
    skillShareCenterLoading,
    refreshSkillShareCenter,
    skillShareCenterError,
    currentSkillShareList,
    skillShareActionState,
    getSkillShareStatusMeta,
    formatDateTime,
    previewSkillShare,
    rejectIncomingSkillShare,
    acceptIncomingSkillShare,
    isSkillShareActionable,
  } = props;

  return (
    <Modal
      open={skillShareCenterOpen}
      title={t("admin.memorySkillShareCenterTitle")}
      onCancel={closeSkillShareCenter}
      width={960}
      footer={[
        <Button key="close" onClick={closeSkillShareCenter}>
          {t("common.close")}
        </Button>,
      ]}
    >
      <div className="memory-skill-share-center">
        <div className="memory-skill-share-toolbar">
          <Segmented<"incoming" | "outgoing">
            value={skillShareCenterTab}
            onChange={(value) => setSkillShareCenterTab(value)}
            options={[
              {
                label: t("admin.memorySkillShareCenterIncoming", {
                  count: incomingPendingCount,
                }),
                value: "incoming",
              },
              {
                label: t("admin.memorySkillShareCenterOutgoing", {
                  count: outgoingSkillShares.length,
                }),
                value: "outgoing",
              },
            ]}
          />
          <Button
            loading={skillShareCenterLoading}
            onClick={() => void refreshSkillShareCenter({ showErrorToast: true })}
          >
            {t("admin.memorySkillShareRefresh")}
          </Button>
        </div>

        {skillShareCenterError ? (
          <Alert
            type="error"
            showIcon
            message={skillShareCenterError}
            action={
              <Button
                size="small"
                onClick={() => void refreshSkillShareCenter({ showErrorToast: true })}
              >
                {t("common.retry")}
              </Button>
            }
          />
        ) : null}

        {skillShareCenterLoading && !currentSkillShareList.length ? (
          <Skeleton active paragraph={{ rows: 6 }} />
        ) : currentSkillShareList.length ? (
          <div className="memory-skill-share-list">
            {currentSkillShareList.map((share) => {
              const statusMeta = getSkillShareStatusMeta(share.status);
              const shareAction = skillShareActionState[share.id];
              const latestTime = share.decidedAt || share.updatedAt;

              return (
                <div key={share.id} className="memory-skill-share-card">
                  <div className="memory-skill-share-card-head">
                    <div className="memory-skill-share-card-title">
                      <strong>
                        {share.skillName || t("admin.memorySkillShareUnknownSkill")}
                      </strong>
                      <span>
                        {share.skillDescription || t("admin.memorySkillShareNoDescription")}
                      </span>
                    </div>
                    <Space size={8} wrap>
                      <Tag color={statusMeta.color}>{statusMeta.text}</Tag>
                    </Space>
                  </div>

                  <div className="memory-skill-share-card-body">
                    {skillShareCenterTab === "incoming" ? (
                      <div className="memory-skill-share-card-line">
                        <strong>{t("admin.memorySkillShareSender")}</strong>
                        <span>
                          {share.sender?.name || t("admin.memorySkillShareUnknownSender")}
                        </span>
                      </div>
                    ) : null}
                    <div className="memory-skill-share-card-line">
                      <strong>{t("admin.memorySkillShareRecipients")}</strong>
                      <div className="memory-tag-group">
                        {share.recipients.length ? (
                          share.recipients.map((recipient: any, index: number) => (
                            <Tag
                              key={`${share.id}-${recipient.type}-${recipient.id}-${index}`}
                            >
                              {recipient.name}
                            </Tag>
                          ))
                        ) : (
                          <span className="memory-content-preview">
                            {t("admin.memorySkillShareUnknownRecipient")}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="memory-skill-share-card-line">
                      <strong>{t("admin.memorySkillShareMessage")}</strong>
                      <span>
                        {share.message || t("admin.memorySkillShareNoMessage")}
                      </span>
                    </div>
                    <div className="memory-skill-share-card-line">
                      <strong>{t("admin.memorySkillShareSharedAt")}</strong>
                      <span>{formatDateTime(share.createdAt)}</span>
                    </div>
                    {latestTime ? (
                      <div className="memory-skill-share-card-line">
                        <strong>{t("admin.memorySkillShareHandledAt")}</strong>
                        <span>{formatDateTime(latestTime)}</span>
                      </div>
                    ) : null}
                  </div>

                  <div className="memory-skill-share-card-actions">
                    <Button
                      size="small"
                      loading={shareAction === "preview"}
                      disabled={Boolean(shareAction) && shareAction !== "preview"}
                      onClick={() => void previewSkillShare(share)}
                    >
                      {t("admin.memorySkillSharePreview")}
                    </Button>
                    {skillShareCenterTab === "incoming" ? (
                      <>
                        <Popconfirm
                          title={t("admin.memorySkillShareRejectConfirmTitle")}
                          okText={t("admin.memorySkillShareReject")}
                          cancelText={t("common.cancel")}
                          okButtonProps={{ danger: true }}
                          onConfirm={() => void rejectIncomingSkillShare(share)}
                        >
                          <Button
                            size="small"
                            danger
                            loading={shareAction === "reject"}
                            disabled={Boolean(shareAction)}
                          >
                            {t("admin.memorySkillShareReject")}
                          </Button>
                        </Popconfirm>
                        <Button
                          type="primary"
                          size="small"
                          loading={shareAction === "accept"}
                          disabled={
                            !isSkillShareActionable(share.status) || Boolean(shareAction)
                          }
                          onClick={() => void acceptIncomingSkillShare(share)}
                        >
                          {t("admin.memorySkillShareAccept")}
                        </Button>
                      </>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              skillShareCenterTab === "incoming"
                ? t("admin.memorySkillShareEmptyIncoming")
                : t("admin.memorySkillShareEmptyOutgoing")
            }
          />
        )}
      </div>
    </Modal>
  );
}

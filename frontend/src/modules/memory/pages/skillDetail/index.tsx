import { useEffect, useMemo, useState } from "react";
import { Alert, Button, Empty, Input, Space, Tag, message } from "antd";
import { useParams } from "react-router-dom";
import MarkdownViewer from "@/modules/knowledge/components/MarkdownViewer";
import { getLocalizedErrorMessage } from "@/components/request";
import RouteLoading from "../../components/RouteLoading";
import { useMemoryManagementOutletContext } from "../../context";
import { getSkillAssetDetail, patchSkillAsset } from "../../skillApi";
import type { StructuredAsset } from "../../shared";

const markdownExtensions = new Set(["md", "markdown"]);

const hasMarkdownShape = (content: string) =>
  /^#{1,6}\s+\S/m.test(content) ||
  /```[\s\S]*?```/.test(content) ||
  /^\s*[-*+]\s+\S/m.test(content) ||
  /^\s*\d+\.\s+\S/m.test(content) ||
  /\[[^\]]+\]\([^)]+\)/.test(content) ||
  /^\s*>\s+\S/m.test(content);

const isMarkdownSkill = (asset: StructuredAsset) => {
  const ext = (asset.fileExt || "").trim().toLowerCase().replace(/^\./, "");
  return markdownExtensions.has(ext) || hasMarkdownShape(asset.content || "");
};

export default function MemorySkillDetailPage() {
  const { itemId = "" } = useParams();
  const {
    t,
    skillAssets,
    skillsInitialized,
    navigateToMemoryList,
    openModal,
    refreshSkillAssets,
  } = useMemoryManagementOutletContext();
  const [detail, setDetail] = useState<StructuredAsset | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [retryKey, setRetryKey] = useState(0);
  const [isInlineEditing, setIsInlineEditing] = useState(false);
  const [inlineContentDraft, setInlineContentDraft] = useState("");
  const [inlineSaving, setInlineSaving] = useState(false);

  const cachedSkill = useMemo(
    () => skillAssets.find((item: StructuredAsset) => item.id === itemId) || null,
    [itemId, skillAssets],
  );
  const skill = detail || cachedSkill;
  const renderAsMarkdown = skill ? isMarkdownSkill(skill) : false;

  useEffect(() => {
    if (!skill || isInlineEditing) {
      return;
    }
    setInlineContentDraft(skill.content || "");
  }, [isInlineEditing, skill]);

  useEffect(() => {
    let ignore = false;

    if (!itemId) {
      setDetail(null);
      setErrorMessage("");
      return () => {
        ignore = true;
      };
    }

    setDetail(cachedSkill);

    if (!skillsInitialized && !cachedSkill) {
      return () => {
        ignore = true;
      };
    }

    setLoading(true);
    setErrorMessage("");
    void (async () => {
      try {
        const nextDetail = await getSkillAssetDetail(itemId);
        if (ignore) {
          return;
        }
        setDetail(nextDetail);
      } catch (error) {
        if (ignore) {
          return;
        }
        console.error("Load skill detail failed:", error);
        setErrorMessage(
          getLocalizedErrorMessage(error, t("admin.memorySkillDetailLoadFailed")) ||
            t("admin.memorySkillDetailLoadFailed"),
        );
      } finally {
        if (!ignore) {
          setLoading(false);
        }
      }
    })();

    return () => {
      ignore = true;
    };
  }, [cachedSkill, itemId, retryKey, skillsInitialized, t]);

  if ((loading || !skillsInitialized) && !skill && !errorMessage) {
    return <RouteLoading title={t("admin.memorySkillDetailTitle")} />;
  }

  const handleStartInlineEdit = () => {
    setInlineContentDraft(skill?.content || "");
    setIsInlineEditing(true);
  };

  const handleCancelInlineEdit = () => {
    setInlineContentDraft(skill?.content || "");
    setIsInlineEditing(false);
  };

  const handleSaveInlineEdit = async () => {
    if (!skill) {
      return;
    }

    if (inlineSaving) {
      return;
    }

    const trimmedDraft = inlineContentDraft.trim();
    if (trimmedDraft === (skill.content || "").trim()) {
      setIsInlineEditing(false);
      return;
    }

    const patchPayload: Record<string, unknown> = {
      name: skill.name,
      content: inlineContentDraft,
      description: skill.description,
      tags: skill.tags,
      is_locked: Boolean(skill.protect),
      file_ext: skill.fileExt || "md",
    };

    if (!skill.parentId) {
      patchPayload.category = skill.category;
      patchPayload.is_enabled = skill.isEnabled ?? true;
    }

    setInlineSaving(true);
    try {
      await patchSkillAsset(skill.id, patchPayload);
      const latestDetail = await getSkillAssetDetail(skill.id);
      if (latestDetail) {
        setDetail(latestDetail);
      } else {
        setDetail((previous) =>
          previous
            ? {
                ...previous,
                content: inlineContentDraft,
              }
            : previous,
        );
      }
      await refreshSkillAssets();
      setIsInlineEditing(false);
      message.success(t("common.saveSuccess"));
    } catch (error) {
      console.error("Save skill detail inline edit failed:", error);
      message.error(
        getLocalizedErrorMessage(error, t("common.saveFailed")) || t("common.saveFailed"),
      );
    } finally {
      setInlineSaving(false);
    }
  };

  return (
    <div className="memory-skill-detail-layout">
      <div className="memory-page-header">
        <div>
          <h2 className="admin-page-title">{t("admin.memorySkillDetailTitle")}</h2>
          <p className="memory-page-subtitle">
            {skill?.name || t("admin.memorySkillShareUnknownSkill")}
          </p>
        </div>
        <Space>
          <Button onClick={() => navigateToMemoryList("skills")}>
            {t("common.back")}
          </Button>
          {skill ? (
            <Button type="primary" onClick={() => openModal("edit", skill)}>
              {t("admin.memoryEditItem")}
            </Button>
          ) : null}
        </Space>
      </div>

      {errorMessage ? (
        <Alert
          type="error"
          showIcon
          message={errorMessage}
          action={
            <Button size="small" onClick={() => setRetryKey((value) => value + 1)}>
              {t("common.retry")}
            </Button>
          }
        />
      ) : null}

      {!skill && !loading ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t("admin.memoryDiffTargetMissing")}
        />
      ) : skill ? (
        <div className="memory-skill-detail-card">
          <div className="memory-skill-detail-title">
            <div>
              <h3>{skill.name}</h3>
              {skill.description ? <p>{skill.description}</p> : null}
            </div>
            <div className="memory-skill-detail-meta">
              {skill.category ? (
                <Tag className="memory-category-tag" bordered={false}>
                  {skill.category}
                </Tag>
              ) : null}
              {skill.protect ? (
                <Tag className="memory-protect-tag" bordered={false}>
                  {t("admin.memoryProtect", { defaultValue: "保护" })}
                </Tag>
              ) : null}
            </div>
          </div>

          {skill.tags.length ? (
            <div className="memory-form-field memory-form-field-full">
              <label>{t("admin.memoryTagSet")}</label>
              <div className="memory-tag-group">
                {skill.tags.map((item: string) => (
                  <Tag key={item}>{item}</Tag>
                ))}
              </div>
            </div>
          ) : null}

          <div className="memory-form-field memory-form-field-full">
            <div className="memory-skill-detail-editor-toolbar">
              <label>
                {renderAsMarkdown
                  ? t("admin.memorySkillDetailMarkdownPreview")
                  : t("admin.memorySkillDetailPlainPreview")}
              </label>
              <Space size={8}>
                {isInlineEditing ? (
                  <>
                    <Button onClick={handleCancelInlineEdit} disabled={inlineSaving}>
                      {t("common.cancel")}
                    </Button>
                    <Button
                      type="primary"
                      loading={inlineSaving}
                      onClick={() => void handleSaveInlineEdit()}
                    >
                      {t("common.save")}
                    </Button>
                  </>
                ) : (
                  <Button onClick={handleStartInlineEdit}>
                    {t("common.edit")}
                  </Button>
                )}
              </Space>
            </div>
            <div className="memory-skill-detail-content">
              {isInlineEditing ? (
                <Input.TextArea
                  value={inlineContentDraft}
                  onChange={(event) => setInlineContentDraft(event.target.value)}
                  autoSize={{ minRows: 18 }}
                  className="memory-skill-detail-textarea"
                />
              ) : renderAsMarkdown ? (
                <MarkdownViewer>{skill.content || ""}</MarkdownViewer>
              ) : (
                <pre>{skill.content || "-"}</pre>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

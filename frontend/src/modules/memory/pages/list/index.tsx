import {
  Button,
  Empty,
  Input,
  Select,
  Space,
  Switch,
  Table,
  Tooltip,
} from "antd";
import { QuestionCircleOutlined } from "@ant-design/icons";
import { useMemoryManagementOutletContext } from "../../context";
import type { ExperienceAsset, StructuredAsset } from "../../shared";
import GlossaryListSection from "../../components/GlossaryListSection";

export default function MemoryManagementListPage() {
  const {
    t,
    activeTab,
    openSkillShareCenter,
    incomingPendingCount,
    glossaryChangeProposals,
    openModal,
    currentTabMeta,
    memoryTabOrder,
    tabMeta,
    setActiveTab,
    setGlossaryDetailTarget,
    setGlossaryInboxOpen,
    resetFilters,
    navigateToMemoryList,
    experienceFeatureEnabled,
    experienceSettingSaving,
    handleExperienceFeatureToggle,
    searchInput,
    setSearchInput,
    query,
    setQuery,
    category,
    setCategory,
    tag,
    setTag,
    glossarySource,
    setGlossarySource,
    availableGlossarySourceOptions,
    availableCategories,
    availableTags,
    glossaryLoading,
    glossaryLoadError,
    refreshGlossaryAssets,
    filteredExperienceItems,
    experienceLoading,
    experienceColumns,
    filteredGlossaryItems,
    glossaryColumns,
    skillLoading,
    skillAssets,
    filteredSkillTree,
    filteredStructuredItems,
    genericColumns,
    toolColumns,
  } = useMemoryManagementOutletContext();

  return (
    <>
      <div className="memory-page-header">
        <div>
          <div className="memory-page-title-row">
            <h2 className="admin-page-title">{t("admin.memoryManagement")}</h2>
            <Tooltip placement="top" title={t("admin.memoryManagementHelp")}>
              <button
                aria-label={t("admin.memoryManagementHelpAriaLabel")}
                className="memory-page-title-help"
                type="button"
              >
                <QuestionCircleOutlined />
              </button>
            </Tooltip>
          </div>
          <p className="memory-page-subtitle">
            {t("admin.memoryManagementSubtitle")}
          </p>
        </div>
        <Space>
          {activeTab === "skills" ? (
            <Button onClick={() => openSkillShareCenter("incoming")}>
              {t("admin.memorySkillShareInboxButton", {
                count: incomingPendingCount,
              })}
            </Button>
          ) : null}
          {activeTab === "glossary" ? (
            <Button onClick={() => setGlossaryInboxOpen(true)}>
              {t("admin.memoryGlossaryInboxButton", {
                count: glossaryChangeProposals.length,
              })}
            </Button>
          ) : null}
          {activeTab !== "tools" && activeTab !== "experience" ? (
            <Button
              type="primary"
              className="admin-page-primary-button"
              onClick={() => openModal("add")}
            >
              {activeTab === "glossary"
                ? t("admin.memoryCreateGlossaryButton")
                : t("admin.memoryCreateButton", { unit: currentTabMeta.unit })}
            </Button>
          ) : null}
        </Space>
      </div>

      <div className="memory-tab-grid">
        {memoryTabOrder.map((tabKey: string) => {
          const tabItem = tabMeta[tabKey];

          return (
            <button
              key={tabKey}
              type="button"
              className={`memory-tab-card ${activeTab === tabKey ? "is-active" : ""}`}
              onClick={() => {
                setActiveTab(tabKey);
                if (tabKey !== "glossary") {
                  setGlossaryDetailTarget(null);
                }
                resetFilters();
                navigateToMemoryList(tabKey);
              }}
            >
              <span className="memory-tab-icon">{tabItem.icon}</span>
              <span className="memory-tab-copy">
                <strong>{tabItem.title}</strong>
                <span>{tabItem.description}</span>
              </span>
            </button>
          );
        })}
      </div>

      {activeTab === "experience" ? (
        <div className="memory-experience-feature-bar">
          <div className="memory-experience-feature-copy">
            <span
              className={`memory-experience-feature-status ${
                experienceFeatureEnabled ? "is-on" : "is-off"
              }`}
            >
              <span className="memory-experience-feature-status-dot" />
              {experienceFeatureEnabled ? t("admin.enabled") : t("admin.disabled")}
            </span>
            <div className="memory-experience-feature-text">
              <strong>{t("admin.memoryHabitFeatureToggle")}</strong>
              <span>
                {experienceFeatureEnabled
                  ? t("admin.memoryHabitFeatureEnabledHint")
                  : t("admin.memoryHabitFeatureDisabledHint")}
              </span>
            </div>
          </div>
          <Switch
            checked={experienceFeatureEnabled}
            loading={experienceSettingSaving}
            checkedChildren={t("admin.enable")}
            unCheckedChildren={t("admin.disable")}
            onChange={(checked) => void handleExperienceFeatureToggle(checked)}
          />
        </div>
      ) : null}

      {activeTab !== "experience" ? (
        <div className="memory-filter-bar">
          <Input.Search
            allowClear
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            onSearch={(value) => setQuery(value)}
            placeholder={t("admin.memorySearchPlaceholder", {
              unit: currentTabMeta.unit,
            })}
            className="memory-filter-search"
          />
          {activeTab === "tools" || activeTab === "skills" ? (
            <>
              <Select
                allowClear
                value={category}
                placeholder={t("admin.memoryAllCategories")}
                options={availableCategories.map((item: string) => ({
                  label: item,
                  value: item,
                }))}
                className="memory-filter-select"
                onChange={(value) => setCategory(value)}
              />
              <Select
                allowClear
                value={tag}
                placeholder={t("admin.memoryAllTags")}
                options={availableTags.map((item: string) => ({
                  label: item,
                  value: item,
                }))}
                className="memory-filter-select"
                onChange={(value) => setTag(value)}
              />
            </>
          ) : activeTab === "glossary" ? (
            <Select
              allowClear
              value={glossarySource}
              placeholder={t("admin.memoryAllSources")}
              options={availableGlossarySourceOptions}
              className="memory-filter-select"
              onChange={(value) => setGlossarySource(value)}
            />
          ) : null}
          <Button onClick={resetFilters}>{t("admin.memoryReset")}</Button>
        </div>
      ) : null}

      {activeTab === "experience" ? (
        <Table<ExperienceAsset>
          className="admin-page-table memory-table"
          rowKey="id"
          loading={experienceLoading}
          dataSource={filteredExperienceItems}
          columns={experienceColumns}
          tableLayout="fixed"
          pagination={{ pageSize: 6, showSizeChanger: false }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={t("admin.memoryEmpty")}
              />
            ),
          }}
        />
      ) : activeTab === "glossary" ? (
        <GlossaryListSection
          t={t}
          columns={glossaryColumns}
          filteredItems={filteredGlossaryItems}
          glossaryLoadError={glossaryLoadError}
          glossaryLoading={glossaryLoading}
          glossarySource={glossarySource}
          query={query}
          refreshGlossaryAssets={refreshGlossaryAssets}
        />
      ) : (
        <Table<StructuredAsset>
          className="admin-page-table memory-table"
          rowKey="id"
          loading={activeTab === "skills" ? skillLoading : false}
          dataSource={activeTab === "skills" ? filteredSkillTree : filteredStructuredItems}
          columns={activeTab === "tools" ? toolColumns : genericColumns}
          expandable={
            activeTab === "skills"
              ? {
                  defaultExpandAllRows: true,
                  rowExpandable: (record) =>
                    skillAssets.some((item: StructuredAsset) => item.parentId === record.id),
                }
              : undefined
          }
          pagination={{ pageSize: 6, showSizeChanger: false }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={t("admin.memoryEmpty")}
              />
            ),
          }}
          scroll={activeTab === "tools" ? { x: 980, y: 420 } : { x: 980 }}
        />
      )}
    </>
  );
}

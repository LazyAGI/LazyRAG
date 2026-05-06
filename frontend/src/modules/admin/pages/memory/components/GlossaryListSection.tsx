import { Alert, Button, Empty, Space, Table } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { TFunction } from "i18next";
import type { GlossaryAsset, GlossarySource } from "../shared";

interface GlossaryListSectionProps {
  t: TFunction;
  assets: GlossaryAsset[];
  columns: ColumnsType<GlossaryAsset>;
  filteredItems: GlossaryAsset[];
  glossaryLoadError: string;
  glossaryLoading: boolean;
  glossarySource?: GlossarySource;
  handleBatchDeleteGlossary: () => void;
  handleBatchMergeGlossary: () => void;
  query: string;
  refreshGlossaryAssets: (options?: {
    keyword?: string;
    silent?: boolean;
    source?: GlossarySource;
  }) => void;
  selectedGlossaryAssetIds: string[];
  selectedGlossaryAssets: GlossaryAsset[];
  setSelectedGlossaryAssetIds: (ids: string[]) => void;
}

export default function GlossaryListSection(props: GlossaryListSectionProps) {
  const {
    t,
    assets,
    columns,
    filteredItems,
    glossaryLoadError,
    glossaryLoading,
    glossarySource,
    handleBatchDeleteGlossary,
    handleBatchMergeGlossary,
    query,
    refreshGlossaryAssets,
    selectedGlossaryAssetIds,
    selectedGlossaryAssets,
    setSelectedGlossaryAssetIds,
  } = props;

  return (
    <>
      {glossaryLoadError ? (
        <Alert
          type="error"
          showIcon
          className="memory-skill-share-alert"
          message={glossaryLoadError}
          action={
            <Button
              size="small"
              onClick={() =>
                refreshGlossaryAssets({
                  keyword: query,
                  source: glossarySource,
                })
              }
            >
              {t("common.retry")}
            </Button>
          }
        />
      ) : null}

      <div className="memory-glossary-batch-toolbar">
        <span>
          {t("admin.memoryGlossaryBatchStats", {
            selected: selectedGlossaryAssets.length,
            total: assets.length,
          })}
        </span>
        <Space size={8} wrap>
          <Button
            type="primary"
            disabled={!selectedGlossaryAssets.length || glossaryLoading}
            onClick={handleBatchMergeGlossary}
          >
            {t("admin.memoryGlossaryBatchMerge")}
          </Button>
          <Button
            danger
            disabled={!selectedGlossaryAssets.length || glossaryLoading}
            onClick={handleBatchDeleteGlossary}
          >
            {t("admin.memoryGlossaryBatchDelete")}
          </Button>
        </Space>
      </div>

      <Table<GlossaryAsset>
        className="admin-page-table memory-table memory-glossary-table"
        rowKey="id"
        loading={glossaryLoading}
        dataSource={filteredItems}
        columns={columns}
        rowSelection={{
          selectedRowKeys: selectedGlossaryAssetIds,
          preserveSelectedRowKeys: true,
          onChange: (selectedRowKeys) =>
            setSelectedGlossaryAssetIds(selectedRowKeys.map((key) => String(key))),
        }}
        tableLayout="fixed"
        pagination={false}
        locale={{
          emptyText: (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={t("admin.memoryEmpty")}
            />
          ),
        }}
        scroll={{ x: 1120, y: 420 }}
      />
    </>
  );
}

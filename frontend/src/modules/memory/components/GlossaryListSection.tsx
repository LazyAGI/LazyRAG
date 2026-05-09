import { useEffect, useState } from "react";
import { Alert, Button, Empty, Space, Table } from "antd";
import type { ColumnsType } from "antd/es/table";
import { getLocalizedTablePagination } from "@/components/ui/pagination";
import type { TFunction } from "i18next";
import type { GlossaryAsset, GlossarySource } from "../shared";

const defaultGlossaryPageSize = 4;

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
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(defaultGlossaryPageSize);

  useEffect(() => {
    setCurrentPage(1);
  }, [glossarySource, query]);

  useEffect(() => {
    const maxPage = Math.max(1, Math.ceil(filteredItems.length / pageSize));
    if (currentPage > maxPage) {
      setCurrentPage(maxPage);
    }
  }, [currentPage, filteredItems.length, pageSize]);

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
          onChange: (selectedRowKeys: Array<string | number>) =>
            setSelectedGlossaryAssetIds(selectedRowKeys.map((key) => String(key))),
        }}
        tableLayout="fixed"
        pagination={getLocalizedTablePagination(
          {
            current: currentPage,
            pageSize,
            total: filteredItems.length,
            showSizeChanger: true,
            pageSizeOptions: [4, 8, 12, 20],
            showTotal: (total: number) => t("common.totalItems", { total }),
            onChange: (page: number, nextPageSize: number) => {
              setCurrentPage(page);
              setPageSize(nextPageSize);
            },
            onShowSizeChange: (_current: number, nextPageSize: number) => {
              setCurrentPage(1);
              setPageSize(nextPageSize);
            },
          },
          t,
        )}
        locale={{
          emptyText: (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={t("admin.memoryEmpty")}
            />
          ),
        }}
        scroll={{ x: 1120, y: 460 }}
      />
    </>
  );
}

import { useEffect, useState } from "react";
import { Alert, Button, Empty, Table } from "antd";
import type { ColumnsType } from "antd/es/table";
import { getLocalizedTablePagination } from "@/components/ui/pagination";
import type { TFunction } from "i18next";
import type { GlossaryAsset, GlossarySource } from "../shared";

const defaultGlossaryPageSize = 4;

interface GlossaryListSectionProps {
  t: TFunction;
  columns: ColumnsType<GlossaryAsset>;
  filteredItems: GlossaryAsset[];
  glossaryLoadError: string;
  glossaryLoading: boolean;
  glossarySource?: GlossarySource;
  query: string;
  refreshGlossaryAssets: (options?: {
    keyword?: string;
    silent?: boolean;
    source?: GlossarySource;
  }) => void;
}

export default function GlossaryListSection(props: GlossaryListSectionProps) {
  const {
    t,
    columns,
    filteredItems,
    glossaryLoadError,
    glossaryLoading,
    glossarySource,
    query,
    refreshGlossaryAssets,
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

      <Table<GlossaryAsset>
        className="admin-page-table memory-table memory-glossary-table"
        rowKey="id"
        loading={glossaryLoading}
        dataSource={filteredItems}
        columns={columns}
        tableLayout="fixed"
        pagination={getLocalizedTablePagination(
          {
            current: currentPage,
            pageSize,
            total: filteredItems.length,
            showSizeChanger: true,
            pageSizeOptions: [4, 8, 12, 20],
            showTotal: (total) => t("common.totalItems", { total }),
            onChange: (page, nextPageSize) => {
              setCurrentPage(page);
              setPageSize(nextPageSize);
            },
            onShowSizeChange: (_current, nextPageSize) => {
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

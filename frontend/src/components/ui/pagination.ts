import type { TablePaginationConfig } from "antd";
import type { TFunction } from "i18next";

export type TablePaginationProp = TablePaginationConfig | false | undefined;

export function getLocalizedTablePagination(
  pagination: TablePaginationProp,
  t: TFunction,
): TablePaginationProp {
  if (!pagination) {
    return pagination;
  }

  return {
    ...pagination,
    locale: {
      ...pagination.locale,
      items_per_page: t("common.itemsPerPageSuffix"),
      page_size: t("common.pageSize"),
    },
  };
}

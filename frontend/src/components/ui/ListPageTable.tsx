import { Table, type TableProps } from "antd";
import { useStyles } from "./useStyles";

const listTableCss = `
.list-page-table {
  width: 100%;
  min-width: 0;
  background-color: var(--color-bg-container, #fff);
  border-radius: 8px;
}
.list-page-table-scroll {
  width: 100%;
  min-width: 0;
  overflow-x: auto;
  overflow-y: hidden;
}
.list-page-table-inner {
  width: 100%;
  min-width: 0;
}
.list-page-table .ant-table-wrapper,
.list-page-table .ant-spin-nested-loading,
.list-page-table .ant-spin-container {
  width: 100%;
  min-width: 0;
}
.list-page-table-title {
  font-size: 14px;
  margin-bottom: 8px;
  color: var(--color-text, #333);
}
`;

const resolveMinWidth = (scrollX?: string | number | true) => {
  if (typeof scrollX === "number") {
    return `${scrollX}px`;
  }
  if (typeof scrollX === "string") {
    return scrollX;
  }
  return undefined;
};

export interface ListPageTableProps extends Omit<
  TableProps,
  "dataSource" | "columns" | "title"
> {
  dataSource: TableProps["dataSource"];
  columns: TableProps["columns"];
  backgroundColor?: string;
  borderRadius?: number | string;
  padding?: number | string;
  title?: React.ReactNode;
  tableHeaderBackgroundColor?: string;
  rootClassName?: string;
  style?: React.CSSProperties;
}

export default function ListPageTable(props: ListPageTableProps) {
  const {
    dataSource,
    columns,
    title,
    rootClassName = "",
    style,
    scroll,
    ...restProps
  } = props;
  useStyles("list-page-table-styles", listTableCss);
  const minWidth = scroll ? resolveMinWidth(scroll.x) : undefined;

  return (
    <div className={`list-page-table ${rootClassName}`} style={style}>
      {title && <div className="list-page-table-title">{title}</div>}
      <div className="list-page-table-scroll">
        <div className="list-page-table-inner" style={minWidth ? { minWidth } : undefined}>
          <Table dataSource={dataSource} columns={columns} scroll={scroll} {...restProps} />
        </div>
      </div>
    </div>
  );
}

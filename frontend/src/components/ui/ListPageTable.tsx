import { Table, type TableProps } from "antd";
import { useStyles } from "./useStyles";

const listTableCss = `
.list-page-table {
  padding: 16px;
  background-color: var(--color-bg-container, #fff);
  border-radius: 8px;
}
.list-page-table-title {
  font-size: 14px;
  margin-bottom: 8px;
  color: var(--color-text, #333);
}
`;

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
    ...restProps
  } = props;
  useStyles("list-page-table-styles", listTableCss);

  return (
    <div className={`list-page-table ${rootClassName}`} style={style}>
      {title && <div className="list-page-table-title">{title}</div>}
      <Table dataSource={dataSource} columns={columns} {...restProps} />
    </div>
  );
}

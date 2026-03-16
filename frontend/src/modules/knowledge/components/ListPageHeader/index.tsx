import { FC, ReactElement } from "react";
import { Input, Select, Form, Button } from "antd";
import "./index.scss";

const { Search } = Input;

interface OptionItem {
  value: string;
  label: string;
}
interface Props {
  /** search params */
  placeholder?: string;
  allowClear?: boolean;

  /** extra */
  extra?: ReactElement | string;

  prefix?: ReactElement | string;

  /** 排序数据项 */
  sortOption?: OptionItem[];
  sortDefaultValue?: string;

  /** 表单字段 */
  searchKey: string;
  sortKey?: string;

  /** 按钮信息 */
  btnText?: string;
  onClick?: () => void;
  onSearch: () => void;
}

const ListPageHeaderComponent: FC<Props> = ({
  placeholder = "请输入",
  extra,
  sortOption,
  sortDefaultValue,
  searchKey = "keyword",
  sortKey = "sort",
  btnText = "创建",
  allowClear = true,
  onClick,
  onSearch,
  prefix,
}) => {
  const defaultSortValue = sortDefaultValue
    ? sortDefaultValue
    : sortOption && sortOption?.length > 0
      ? sortOption[0].value
      : "";
  return (
    <div className="filter-container">
      {prefix}
      <Form.Item name={searchKey} label="搜索" style={{ marginBottom: 0 }}>
        <Search
          placeholder={placeholder}
          allowClear={allowClear}
          className="search-input ghost-custom-border"
          variant="borderless"
          onSearch={onSearch}
        />
      </Form.Item>
      {extra}
      <div className="right-box">
        {sortOption && sortOption.length > 0 && (
          <div className="sort-box">
            <span>按</span>
            <Form.Item name={sortKey} noStyle initialValue={defaultSortValue}>
              <Select
                options={sortOption}
                variant={"underlined"}
                className="sort-select"
                onSearch={onSearch}
              />
            </Form.Item>
            <span>排序</span>
          </div>
        )}
        {btnText && onClick && (
          <Button type="primary" onClick={onClick}>
            {btnText}
          </Button>
        )}
      </div>
    </div>
  );
};

export default ListPageHeaderComponent;

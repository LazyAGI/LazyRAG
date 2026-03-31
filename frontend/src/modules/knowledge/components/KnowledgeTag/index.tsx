import { Tag, Tooltip } from "antd";

import "./index.scss";

interface Props {
  title: string;
  checkable: boolean;
  checked?: (tag: string) => boolean;
  onChange?: (checked: boolean) => void;
}

const KnowledgeTag = (props: Props) => {
  return (
    <>
      {props.checkable ? (
        <Tag.CheckableTag
          className="knowledge-tag"
          checked={props.checked ? props.checked(props.title) : false}
          onChange={(checked) =>
            props.onChange ? props.onChange(checked) : {}
          }
        >
          <Tooltip placement="topLeft" title={props.title}>
            {props.title}
          </Tooltip>
        </Tag.CheckableTag>
      ) : (
        <Tag className="knowledge-tag">
          <Tooltip placement="topLeft" title={props.title}>
            {props.title}
          </Tooltip>
        </Tag>
      )}
    </>
  );
};

export default KnowledgeTag;

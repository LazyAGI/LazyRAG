/**
 * 简易 Markdown 编辑占位：与 @mdxeditor/editor 同接口（value/onChange）。
 * 若需完整 MDX 编辑器，可安装 @mdxeditor/editor 并恢复原实现。
 */
import { useState, useEffect } from "react";
import { Input } from "antd";

const { TextArea } = Input;

interface IProps {
  value: string;
  onChange: (value: string) => void;
}

const MdxEditor = (props: IProps) => {
  const { value = "", onChange } = props;
  const [local, setLocal] = useState(value);

  useEffect(() => {
    setLocal(value);
  }, [value]);

  return (
    <div className="mdx-editor-wrapper" style={{ isolation: "isolate" }}>
      <TextArea
        value={local}
        onChange={(e) => {
          const v = e.target.value;
          setLocal(v);
          onChange(v);
        }}
        placeholder="Markdown 内容"
        autoSize={{ minRows: 6 }}
        style={{ width: "100%" }}
      />
    </div>
  );
};

export default MdxEditor;

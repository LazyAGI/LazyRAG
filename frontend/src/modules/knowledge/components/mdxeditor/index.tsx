
import { useState, useEffect } from "react";
import { Input } from "antd";
import { useTranslation } from "react-i18next";

const { TextArea } = Input;

interface IProps {
  value: string;
  onChange: (value: string) => void;
}

const MdxEditor = (props: IProps) => {
  const { t } = useTranslation();
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
        placeholder={t("knowledge.markdownPlaceholder")}
        autoSize={{ minRows: 6 }}
        style={{ width: "100%" }}
      />
    </div>
  );
};

export default MdxEditor;

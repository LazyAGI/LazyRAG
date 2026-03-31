import { ALL_TAGS } from "@/modules/knowledge/constants/common";
import { Select } from "antd";
import { useState } from "react";
import { useTranslation } from "react-i18next";

interface TagSelectProps {
  tags: string[];
  value?: string[];
  onChange?: (value: string[]) => void;
}

const TagSelect = ({ tags, value = [], onChange }: TagSelectProps) => {
  const { t } = useTranslation();
  const MAX_TAG_LENGTH = 100;

  const [searchValue, setSearchValue] = useState("");

  function handleSearch(val: string) {
    if (val.length <= MAX_TAG_LENGTH) {
      setSearchValue(val);
    } else {
      setSearchValue("");
    }
  }

  return (
    <Select
      mode="tags"
      tokenSeparators={[","]}
      searchValue={searchValue}
      value={value}
      onChange={onChange}
      maxCount={10}
      onSearch={handleSearch}
      options={tags
        .filter((tag) => tag !== ALL_TAGS)
        .map((tag) => {
          return { value: tag, name: tag };
        })}
      onInputKeyDown={(e) => {
        if (searchValue.length >= MAX_TAG_LENGTH && e.key !== "Backspace") {
          e.preventDefault();
        }
      }}
      onSelect={() => setSearchValue("")}
      placeholder={t("knowledge.selectTagPlaceholder")}
    />
  );
};

export default TagSelect;

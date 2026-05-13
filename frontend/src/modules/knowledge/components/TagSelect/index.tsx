import { ALL_TAGS } from "@/modules/knowledge/constants/common";
import { message, Select } from "antd";
import { useState } from "react";
import { useTranslation } from "react-i18next";

interface TagSelectProps {
  tags: string[];
  value?: string[];
  onChange?: (value: string[]) => void;
}

const TagSelect = ({ tags, value = [], onChange }: TagSelectProps) => {
  const { t } = useTranslation();
  const MAX_TAG_COUNT = 10;
  const MAX_TAG_LENGTH = 100;

  const [searchValue, setSearchValue] = useState("");

  function handleSearch(val: string) {
    if (val.length <= MAX_TAG_LENGTH) {
      setSearchValue(val);
    } else {
      setSearchValue("");
    }
  }

  function handleChange(nextValue: string[]) {
    const normalizedTags = Array.from(
      new Set((nextValue || []).map((tag) => tag.trim()).filter(Boolean)),
    );
    const validLengthTags = normalizedTags.filter(
      (tag) => tag.length <= MAX_TAG_LENGTH,
    );

    if (validLengthTags.length < normalizedTags.length) {
      message.warning(
        t("knowledge.singleTagMaxLength", { count: MAX_TAG_LENGTH }),
      );
    }

    if (validLengthTags.length > MAX_TAG_COUNT) {
      message.warning(t("knowledge.maxTenTags"));
      setSearchValue("");
      onChange?.(validLengthTags.slice(0, MAX_TAG_COUNT));
      return;
    }

    onChange?.(validLengthTags);
  }

  return (
    <Select
      mode="tags"
      tokenSeparators={[","]}
      searchValue={searchValue}
      value={value}
      onChange={handleChange}
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

import { useEffect, useMemo, useState } from "react";
import i18n from "@/i18n";

interface RenderTxtProps {
  fileData: ArrayBuffer;
  content: string | null;
}

const RenderTxt = (props: RenderTxtProps) => {
  const { fileData, content } = props;
  const [originalText, setOriginalText] = useState("");

  const contentText = useMemo(() => content || "", [content]);

  useEffect(() => {
    if (fileData) {
      setOriginalText(new TextDecoder().decode(fileData));
    }
  }, [fileData]);

  const highlightedText = useMemo(() => {
    if (!contentText || !originalText) {
      return originalText;
    }

    const txtList = originalText.split(contentText);
    if (txtList.length <= 1) {
      return originalText;
    }
    const newText = txtList.map((txt, index) => {
      if (index === 0) {
        return txt;
      }
      return `<span style="background-color: yellow; font-weight: bold;" class="txt-keyword">${contentText}</span>${txt}`;
    });

    setTimeout(() => {
      const txtKeywords = document.querySelectorAll(".txt-keyword");
      txtKeywords.forEach((txtKeyword) => {
        txtKeyword.scrollIntoView({ behavior: "smooth", block: "center" });
      });
    }, 200);

    return newText.join("");
  }, [contentText, originalText]);

  try {
    return (
      <div className="file-viewer-text-container">
        <pre dangerouslySetInnerHTML={{ __html: highlightedText || "" }}></pre>
      </div>
    );
  } catch {
    return (
      <div
        style={{
          padding: "20px",
          color: "#ff4d4f",
          textAlign: "center",
        }}
      >
        {i18n.t("knowledge.previewLoadFailed")}
      </div>
    );
  }
};

export default RenderTxt;

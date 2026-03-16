import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import jsPreviewDocx, { JsDocxPreview } from "@js-preview/docx";
import "@js-preview/docx/lib/index.css";
import jsPreviewExcel, { JsExcelPreview } from "@js-preview/excel";
import { Segment } from "@/api/generated/knowledge-client";

type JsPreviewType = JsDocxPreview | JsExcelPreview;

interface RenderOfficeProps {
  fileData: ArrayBuffer;
  fileType: "docx" | "excel";
  content: Segment["content"] | null;
  metadata: Record<string, unknown> | null;
}

const RenderOffice = (props: RenderOfficeProps) => {
  const { fileData, fileType, content, metadata } = props;
  const reader = useRef<JsPreviewType | null>(null);
  const showFile = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(false);

  const contentText = useMemo(() => content || "", [content]);
  const metaTitle = useMemo(
    () => (metadata?.title as string) || "",
    [metadata],
  );

  // 获取对应的预览器
  const getReaderType = useCallback(() => {
    switch (fileType) {
      case "docx":
        return jsPreviewDocx;
      case "excel":
        return jsPreviewExcel;
      default:
        return null;
    }
  }, [fileType]);

  // 高亮关键词函数
  const highlightKeyword = useCallback(
    (container: HTMLDivElement, keyword: string, title = "") => {
      if (!container || !keyword || typeof keyword !== "string") {
        return;
      }

      clearHighlight(container);

      // 匹配docx特定的元素：标题和段落
      const elements = container.querySelectorAll(
        "span, p",
      ) as NodeListOf<HTMLElement>;

      const textsToMatch: string[] = [];
      if (title && typeof title === "string" && keyword.includes(title)) {
        textsToMatch.push(title);
        const remainingText = keyword
          .replace(title, "")
          .replace(/[\s\n]+/g, " ")
          .trim();
        if (remainingText) {
          textsToMatch.push(remainingText);
        }
      } else {
        textsToMatch.push(keyword.replace(/[\s\n]+/g, " ").trim());
      }

      // 匹配每个文本
      textsToMatch.forEach((text) => {
        elements.forEach((element) => {
          if (element.innerText === text) {
            console.log("Highlighting element:", element, text);
            element.style.backgroundColor = "yellow";
            element.scrollIntoView({ behavior: "smooth", block: "center" });
          }
        });
      });
    },
    [],
  );

  // 清除高亮函数
  const clearHighlight = useCallback((container: HTMLElement) => {
    const elements = container.querySelectorAll("*") as NodeListOf<HTMLElement>;
    elements.forEach((element) => {
      element.style.backgroundColor = "";
    });
  }, []);

  // 处理文件预览
  const previewFile = useCallback(async () => {
    if (!fileData) {
      return;
    }

    // 清理之前的预览器
    if (reader.current) {
      reader.current.destroy?.();
      reader.current = null;
    }

    try {
      setLoading(true);

      const readerType = getReaderType();
      if (!readerType || !showFile.current) {
        return;
      }

      // 清理容器
      showFile.current.innerHTML = "";

      reader.current = readerType.init(showFile.current, {
        inWrapper: true,
        ignoreWidth: true,
        ignoreHeight: true,
        ignoreFonts: false,
      });

      if (reader.current && reader.current.preview) {
        await reader.current.preview(fileData);
      }
    } catch (err) {
      console.error("Office preview error:", err);
    } finally {
      setLoading(false);
    }
  }, [fileData, fileType, getReaderType]);

  // 当文件数据变化时开始预览
  useEffect(() => {
    if (fileData) {
      previewFile();
    }
  }, [fileData, previewFile]);

  // 当关键词变化时更新高亮（不影响 loading 状态）
  useEffect(() => {
    if (!showFile.current || !contentText?.trim()) {
      return;
    }

    if (showFile.current.children.length > 0) {
      setTimeout(() => {
        if (showFile.current) {
          highlightKeyword(showFile.current, contentText, metaTitle);
        }
      }, 100);
    }
  }, [contentText, metaTitle, highlightKeyword]);

  // 清理函数
  useEffect(() => {
    return () => {
      if (reader.current) {
        reader.current.destroy?.();
        reader.current = null;
      }
    };
  }, []);

  return (
    <div className="file-viewer-container">
      <div ref={showFile} className="file-viewer-content"></div>
      {loading && (
        <div
          style={{
            position: "absolute",
            top: "50%",
            left: "50%",
            transform: "translate(-50%, -50%)",
            zIndex: 10,
          }}
        >
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              fontSize: "16px",
              color: "#666",
            }}
          >
            <div style={{ marginBottom: "12px" }}>加载中...</div>
          </div>
        </div>
      )}
    </div>
  );
};

export default RenderOffice;

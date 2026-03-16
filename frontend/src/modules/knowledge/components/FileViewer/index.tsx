import { useEffect, useMemo, useState } from "react";
import { Spin, message, Empty } from "antd";
import FileUtils from "@/modules/knowledge/utils/file";
import { Segment } from "@/api/generated/knowledge-client";
import {
  RenderHtml,
  RenderTxt,
  RenderOffice,
  RenderPpt,
  RenderExcel,
} from "./renderers";

import { RenderPdf } from "@/components/ui";

import "./index.scss";

interface FileViewerProps {
  file?: string;
  fileName: string;
  segment?: Segment;
}

const FileViewer = (props: FileViewerProps) => {
  const { file, segment } = props;
  const [loading, setLoading] = useState(false);
  const [fileData, setFileData] = useState<ArrayBuffer | null>(null);
  const [meta, setMeta] = useState<Record<string, unknown> | null>(null);
  const [content, setContent] = useState<string | null>(null);

  useEffect(() => {
    if (!segment) {
      setMeta(null);
      setContent(null);
      return;
    }
    if (segment?.meta) {
      try {
        const parsedMeta = JSON.parse(segment.meta);
        setMeta(parsedMeta);
      } catch {
        const uiMessage = "加载失败，请重新加载";
        message.error(uiMessage);
        setMeta(null);
      }
    } else {
      setMeta(null);
    }

    if (segment?.content) {
      setContent(segment.content);
    } else {
      setContent(null);
    }
  }, [segment?.meta, segment?.content]);

  // 计算文件类型
  const fileType = useMemo(() => {
    const suffix = FileUtils.getFileTypeFromURI(file as string);
    if (["txt", "md", "json", "log", "csv"].includes(suffix)) {
      return "text";
    }
    if (["html", "xml", "svg"].includes(suffix)) {
      return "html";
    }
    if (["pdf"].includes(suffix)) {
      return "pdf";
    }
    if (["pptx", "ppt"].includes(suffix)) {
      return "pptx";
    }
    if (["docx", "doc"].includes(suffix)) {
      return "docx";
    }
    if (["xlsx", "xls"].includes(suffix)) {
      return "excel";
    }
    return "unknown";
  }, [file]);

  // 统一获取文件数据的函数
  const getFileData = async (
    fileInput: string | ArrayBuffer | File | Blob,
  ): Promise<ArrayBuffer> => {
    try {
      if (fileInput instanceof ArrayBuffer) {
        return Promise.resolve(fileInput);
      }
      if (fileInput instanceof File || fileInput instanceof Blob) {
        return await fileInput.arrayBuffer();
      }
      if (typeof fileInput === "string") {
        const response = await fetch(fileInput, {
          signal: FileUtils.timeoutSignal(5 * 60 * 1000), // 5分钟超时
        });
        if (!response.ok) {
          throw new Error("Network response was not ok");
        }
        return await response.arrayBuffer();
      }
      throw new Error("Unsupported file input type");
    } catch (err) {
      throw new Error(
        `Failed to read file: ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  };

  useEffect(() => {
    if (!file) {
      setFileData(null);
      return;
    }
    setLoading(true);
    getFileData(file as string | ArrayBuffer | File | Blob)
      .then((data) => {
        setFileData(data);
        setLoading(false);
      })
      .catch(() => {
        const uiMessage = "加载失败，请重新加载";
        message.error(uiMessage);
        setLoading(false);
        setFileData(null);
      });
  }, [file]);

  // 渲染加载中
  const renderLoading = useMemo(() => {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2">
        <Spin spinning={loading} />
        <p className="text-gray-500">数据加载中...</p>
      </div>
    );
  }, [loading]);

  // 渲染空状态
  const renderEmpty = useMemo(() => {
    return <Empty description="暂无数据" />;
  }, []);

  const renderFile = useMemo(() => {
    if (!fileData) {
      return null;
    }
    switch (fileType) {
      case "text":
        return <RenderTxt fileData={fileData} content={content} />;
      case "html":
        return <RenderHtml fileData={fileData} content={content} />;
      case "pdf":
        return (
          <RenderPdf
            className="scroll-container"
            style={{
              height: "calc(100vh - 210px)",
            }}
            fileData={fileData}
            metadata={meta}
            content={content}
          />
        );
      case "docx":
        return (
          <RenderOffice
            fileData={fileData}
            fileType={fileType}
            metadata={meta}
            content={content}
          />
        );
      case "excel":
        return (
          <RenderExcel
            fileData={fileData}
            fileType={fileType}
            metadata={meta}
            content={content}
          />
        );
      case "pptx":
        return <RenderPpt fileData={fileData} />;
      case "unknown":
      default:
        return (
          <div
            style={{
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
              height: "200px",
              color: "#ff4d4f",
              fontSize: "14px",
            }}
          >
            暂不支持该文件格式预览
          </div>
        );
    }
  }, [fileData, content]);

  return (
    <>
      {loading && renderLoading}
      {!loading && !fileData && renderEmpty}
      {!loading && fileData && renderFile}
    </>
  );
};

export default FileViewer;

import { useCallback, useEffect, useRef } from "react";
import { init } from "pptx-preview";

interface RenderPptProps {
  fileData: ArrayBuffer;
}

const RenderPpt = (props: RenderPptProps) => {
  const { fileData } = props;

  const showFile = useRef<HTMLDivElement>(null);

  // PPTX 预览函数
  const previewPptx = useCallback(async (arrayBuffer: ArrayBuffer) => {
    if (!showFile.current) {
      return;
    }

    try {
      // 创建预览容器
      const previewContainer = document.createElement("div");
      previewContainer.style.cssText = `
        width: 100%;
        height: 100%;
        overflow: auto;
        background: #f5f5f5;
      `;

      // 初始化 PPTX 预览器
      const pptxPreview = init(previewContainer, {
        width: 800,
        height: 600,
        mode: "slide", // 列表模式
      });

      // 预览 PPTX 文件
      await pptxPreview.preview(arrayBuffer);

      // 清理 loading 并显示预览
      if (showFile.current) {
        // 确保清理所有内容并显示预览
        showFile.current.innerHTML = "";
        showFile.current.appendChild(previewContainer);
      }
    } catch (err) {
      console.error("PPTX preview error:", err);

      // 如果预览失败，显示错误信息
      showFile.current.innerHTML = "";

      const errorContainer = document.createElement("div");
      errorContainer.style.cssText = `
        width: 100%;
        height: 100%;
        overflow: auto;
        padding: 20px;
        background: #f5f5f5;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
      `;

      const infoDiv = document.createElement("div");
      infoDiv.style.cssText = `
        background: white;
        padding: 40px;
        border-radius: 8px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        text-align: center;
        max-width: 500px;
      `;

      const title = document.createElement("h3");
      title.textContent = "PowerPoint 文件预览失败";
      title.style.cssText = `
        margin: 0 0 16px 0;
        color: #d32f2f;
        font-size: 20px;
        font-weight: bold;
      `;

      const description = document.createElement("p");
      description.textContent = `无法预览此 PowerPoint 文件。错误信息: ${err instanceof Error ? err.message : "未知错误"}`;
      description.style.cssText = `
        margin: 0 0 20px 0;
        color: #666;
        font-size: 14px;
        line-height: 1.5;
      `;

      const fileInfo = document.createElement("div");
      fileInfo.style.cssText = `
        background: #f8f9fa;
        padding: 12px;
        border-radius: 4px;
        font-family: monospace;
        font-size: 12px;
        color: #495057;
      `;
      fileInfo.textContent = `文件大小: ${(arrayBuffer.byteLength / 1024).toFixed(1)} KB`;

      infoDiv.appendChild(title);
      infoDiv.appendChild(description);
      infoDiv.appendChild(fileInfo);

      errorContainer.appendChild(infoDiv);
      showFile.current.appendChild(errorContainer);
    }
  }, []);

  useEffect(() => {
    previewPptx(fileData);
  }, [fileData, previewPptx]);

  return (
    <div className="file-viewer-container">
      <div ref={showFile} className="file-viewer-content"></div>
    </div>
  );
};

export default RenderPpt;

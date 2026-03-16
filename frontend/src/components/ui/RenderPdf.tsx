/**
 * Placeholder PDF viewer for LazyRAG. For full PDF support, add react-pdf and copy
 * the full RenderPdf implementation from tieyiyuan shared-ui.
 */
interface RenderPdfProps {
  fileData: string | ArrayBuffer | File | null;
  metadata?: Record<string, unknown> | null;
  content?: string | null;
  defaultPageWidth?: number;
  loadingText?: string;
  className?: string;
  style?: React.CSSProperties;
}

export default function RenderPdf({
  fileData,
  loadingText = "正在加载PDF...",
  className,
  style,
}: RenderPdfProps) {
  if (!fileData) {
    return (
      <div
        className={className}
        style={{ padding: 20, textAlign: "center", color: "#666", ...style }}
      >
        {loadingText}
      </div>
    );
  }
  return (
    <div
      className={className}
      style={{ padding: 20, textAlign: "center", color: "#666", ...style }}
    >
      PDF 预览（请安装 react-pdf 以启用完整预览）
    </div>
  );
}

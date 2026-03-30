import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import classnames from "classnames";
import "katex/dist/katex.min.css";
import { Popover } from "antd";
import rehypeSanitize from "rehype-sanitize";
import "./markdown.scss";
import "./index.scss";
import { useEffect, useState } from "react";
import { customSchema } from "./config";
import rehypeRaw from "rehype-raw";

const ImageComponent = (props: any) => {
  const [imageLoadError, setImageLoadError] = useState(false);
  if (imageLoadError) {
    return null;
  }

  return (
    <img
      {...props}
      onError={() => setImageLoadError(true)}
      onLoad={() => setImageLoadError(false)}
    />
  );
};

const MarkdownViewer = (props: any) => {
  const { children, className = "", sources = [], IS_STREAMING } = props;

  const [markSources, setMarkSources] = useState<any[]>([]);

  useEffect(() => {
    if (sources && sources.length > 0) {
      setMarkSources(sources);
    }
  }, [sources]);

  return (
    <div
      className={classnames("rag-markdown", {
        [className]: !!className,
      })}
    >
      <Markdown
        {...props}
        remarkPlugins={[[remarkGfm, { singleTilde: false }], remarkMath]}
        rehypePlugins={[
          rehypeRaw,
          rehypeKatex,
          [rehypeSanitize, customSchema],
        ]}
        components={{
          a(props: any) {
            const href = props.href;
            if (href === "#source") {
              if (IS_STREAMING) {
                return (
                  <span
                    className="md-segment-index"
                    style={{ backgroundColor: "var(--color-text-description)" }}
                  >
                    {props.children}
                  </span>
                );
              }
              return (
                <Popover
                  title={props.title || ""}
                  content={
                    <div className="md-content-card">
                      <div className="md-content-card-content">
                        <MarkdownViewer>
                          {
                            markSources.find(
                              (source) => source.index == props.children,
                            )?.content
                          }
                        </MarkdownViewer>
                      </div>
                    </div>
                  }
                >
                  <span className="md-segment-index">{props.children}</span>
                </Popover>
              );
            }

            return (
              <a href={props.href} target="_blank">
                {props.children}
              </a>
            );
          },
          script() {
            return null;
          },
          li(props: any) {
            const children = Array.isArray(props.children)
              ? props.children.filter((item: any) => item !== "\n")
              : props.children;

            return <li>{children}</li>;
          },
          img: ImageComponent,
          ...props.components,
        }}
      >
        {children || ""}
      </Markdown>
    </div>
  );
};

export default MarkdownViewer;

import MarkdownIt from "markdown-it";
import MdEditor from "react-markdown-editor-lite";
import "react-markdown-editor-lite/lib/index.css";

const MarkdownEditor = (props: any) => {
  const mdParser = new MarkdownIt(/* Markdown-it options */);
  const { readOnly = false } = props;

  return (
    <MdEditor
      value={props.value || ""}
      style={props.style}
      renderHTML={(text) => mdParser.render(text)}
      onChange={props.onChange}
      readOnly={readOnly}
      view={readOnly ? { menu: false, md: false, html: true } : undefined}
    />
  );
};

export default MarkdownEditor;

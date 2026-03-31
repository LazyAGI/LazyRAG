import {
  UndoRedo,
  BoldItalicUnderlineToggles,
  BlockTypeSelect,
  InsertTable,
} from "@mdxeditor/editor";
import "./index.scss";

const ToolbarComponent = () => {
  return (
    <div className="mdx-editor-toolbar">
      <UndoRedo />
      <BoldItalicUnderlineToggles />
      <BlockTypeSelect />
      <InsertTable />
    </div>
  );
};

export default ToolbarComponent;

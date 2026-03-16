import { Doc } from "@/api/generated/knowledge-client";

const PreviewTab = (props: { detail: Doc }) => {
  const { detail } = props;

  console.log("detail:", detail);

  return <div>PreviewTab</div>;
};

export default PreviewTab;

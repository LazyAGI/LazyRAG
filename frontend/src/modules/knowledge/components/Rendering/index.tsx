import { LoadingOutlined } from "@ant-design/icons";
const Rendering = ({ text = "数据加载中..." }) => {
  return (
    <div className="flex h-full w-full items-center justify-center">
      <LoadingOutlined style={{ color: "var(--color-primary)" }} />
      <span className="ml-2 text-[var(--color-primary)]">{text}</span>
    </div>
  );
};

export default Rendering;

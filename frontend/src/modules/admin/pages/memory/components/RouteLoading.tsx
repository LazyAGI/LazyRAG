import { Skeleton } from "antd";

interface RouteLoadingProps {
  title: string;
}

export default function RouteLoading({ title }: RouteLoadingProps) {
  return (
    <div className="memory-review-page is-route-loading">
      <div className="memory-review-workspace">
        <div className="memory-review-header">
          <div className="memory-review-title">
            <h3>{title}</h3>
          </div>
        </div>
        <Skeleton active paragraph={{ rows: 10 }} />
      </div>
    </div>
  );
}

import { CloseOutlined, FileTextOutlined } from "@ant-design/icons";

import "./index.scss";
import { Tooltip } from "antd";

export interface ChatFile {
  name: string;
  uid: string;
}

interface Props {
  files: ChatFile[];
  onRemove?: (uid: string) => void;
}

const ChatFiles = (props: Props) => {
  const { files, onRemove } = props;

  return (
    <div className="chat-file-list">
      {files.map((item, index) => {
        return (
          <div className="chat-files-item" key={`img-${index}`}>
            <div className="chat-files-name">
              <FileTextOutlined />
              <Tooltip title={item.name}>
                <span className="chat-files-name-title">{item.name}</span>
              </Tooltip>
            </div>
            {onRemove && (
              <div
                className="chat-files-remove"
                onClick={() => onRemove(item.uid)}
              >
                <CloseOutlined />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};

export default ChatFiles;

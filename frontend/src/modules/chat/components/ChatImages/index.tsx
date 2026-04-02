import { Image } from "antd";
import { CloseCircleFilled } from "@ant-design/icons";

import "./index.scss";

export interface ChatImage {
  base64: string;
  uid: string;
}

interface Props {
  images: ChatImage[];
  onRemove?: (uid: string) => void;
}

const ChatImages = (props: Props) => {
  const { images, onRemove } = props;

  return (
    <div className="chat-images-list">
      {images.map((item, index) => {
        return (
          <div className="chat-images-item" key={`img-${index}`}>
            <Image src={item.base64} height={52} />
            {onRemove && (
              <div
                className="chat-images-remove"
                onClick={() => onRemove(item.uid)}
              >
                <CloseCircleFilled />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};

export default ChatImages;

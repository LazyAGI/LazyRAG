import { ImgHTMLAttributes } from "react";

const DEFAULT_ERROR_IMAGE =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";

interface IProps extends ImgHTMLAttributes<HTMLImageElement> {
  showErrorImage?: boolean;
  errorUrl?: string;
}

const CustomImage = (props: IProps) => {
  const { showErrorImage, errorUrl = DEFAULT_ERROR_IMAGE, ...rest } = props;
  return (
    <img
      {...rest}
      alt={props.alt || " "}
      style={{ ...props.style }}
      onError={(e) => {
        const target = e.target as HTMLImageElement;
        if (showErrorImage) {
          target.src = errorUrl;
        } else {
          target.style.display = "none";
        }
      }}
      onLoad={(e) => {
        const target = e.target as HTMLImageElement;
        target.style.display = "";
      }}
    />
  );
};

export default CustomImage;

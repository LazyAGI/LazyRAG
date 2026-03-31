import { useEffect, useRef } from "react";
import { Modal } from "antd";
import { forwardRef, useImperativeHandle, useState } from "react";
import { useTranslation } from "react-i18next";
import { Segment } from "@/api/generated/knowledge-client";

import SegmentContent from "@/modules/knowledge/pages/knowledge/components/SegmentContent";
import Rendering from "@/modules/knowledge/components/Rendering";
import "./index.scss";

export interface ISegmentDetailModalRef {
  handleOpen: (segment: Segment, group: string) => void;
}

const SegmentDetailModal = forwardRef(
  (props: { onClose: () => void; editable: boolean }, ref) => {
    const { editable, onClose } = props;
    const { t } = useTranslation();

    const [visible, setVisible] = useState(false);
    const [segment, setSegment] = useState<Segment | null>(null);
    const [group, setGroup] = useState("");
    const [loading, setLoading] = useState(false);
    const timerRef = useRef<NodeJS.Timeout | null>(null);

    useImperativeHandle(ref, () => {
      return { handleOpen };
    });

    function handleOpen(data: Segment, name: string) {
      setSegment(data);
      setGroup(name);
      setVisible(true);
      setLoading(true);
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
      timerRef.current = setTimeout(() => {
        setLoading(false);
      }, 100);
    }

    useEffect(() => {
      return () => {
        if (timerRef.current) {
          clearTimeout(timerRef.current);
        }
      };
    }, []);

    function handleClose() {
      setSegment(null);
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
      setVisible(false);
      if (editable) {
        onClose();
      }
    }

    return (
      <Modal
        open={visible}
        footer={
          <div className="modalFooter">
            <span className="pageNumber">#{segment?.number || 0}</span>
          </div>
        }
        title={editable ? t("knowledge.segmentDetailEditable") : t("knowledge.segmentDetail")}
        onCancel={handleClose}
        width={editable ? 1280 : 640}
        style={{ minHeight: 380 }}
      >
        <div className="contentCard">
          <div className="content">
            {loading ? (
              <Rendering />
            ) : (
              <SegmentContent
                segment={segment || {}}
                group={group}
                editable={editable}
              />
            )}
          </div>
        </div>
      </Modal>
    );
  },
);

export default SegmentDetailModal;

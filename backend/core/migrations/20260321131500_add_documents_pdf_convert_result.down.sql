-- 20260321131500_add_documents_pdf_convert_result
-- +migrate Down

ALTER TABLE documents
DROP COLUMN IF EXISTS pdf_convert_result;

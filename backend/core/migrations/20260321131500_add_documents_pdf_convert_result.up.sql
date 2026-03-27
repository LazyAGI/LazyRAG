-- 20260321131500_add_documents_pdf_convert_result
-- +migrate Up

ALTER TABLE documents
ADD COLUMN IF NOT EXISTS pdf_convert_result varchar(64) NOT NULL DEFAULT '';

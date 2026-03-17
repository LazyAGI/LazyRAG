// Package acl 提供知识库（KB）与资源的访问控制：可见级别（public/protected/private）、
// ACL 行（用户/租户权限）、用户-组映射等；提供 Can、Permission 等鉴权能力。
// 数据存储在关系型数据库中（由 ACL_DB_DRIVER/ACL_DB_DSN 指定，支持 PostgreSQL、SQLite、MySQL），
// 通过 GORM ORM 操作，表包括 acl_visibility、acl_rows、acl_kbs、acl_user_groups。
package acl

-- 010_train_acceptance.sql -- P6.7 generic three-leg acceptance report.
-- The Store migration driver performs the metadata-guided legacy-column
-- rename before stamping this version; the SQL body stays an auditable no-op
-- so fresh databases (whose 009 schema already uses the new name) also apply.
SELECT 1;

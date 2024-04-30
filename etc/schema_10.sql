ALTER TABLE `movies` ADD COLUMN version int NOT NULL default 1 ;
UPDATE metadata set v=10 where k='schema_version';

ALTER TABLE object_store COMMENT 'Stores objects for deployments that do not use Amazon S3, such as when testing within GitHub Actions.';
ALTER TABLE objects COMMENT 'Stores pointers from a SHA256 to a URN, which can be the object_store or in Amazon S3.';
ALTER TABLE movies ADD COLUMN movie_zipfile_urn varchar(1024) DEFAULT NULL after movie_data_urn;
UPDATE metadata SET v=11 WHERE k='schema_version';

ALTER TABLE `movie_frames` RENAME COLUMN `frame_sha256` TO `frame_urn`;
UPDATE metadata set v=7 where k='schema_version';

DROP TABLE movie_frame_analysis;
DROP TABLE movie_analysis;
ALTER TABLE movie_frame_trackpoints add column movie_id int not null after id;
ALTER TABLE movie_frame_trackpoints add column frame_number int not null after movie_id;

UPDATE movie_frame_trackpoints tp JOIN movie_frames mf ON tp.frame_id = mf.id
 SET tp.movie_id = mf.movie_id, tp.frame_number = mf.frame_number;

ALTER TABLE `movie_frame_trackpoints` DROP FOREIGN KEY `movie_frame_trackpoints_ibfk_1`;

ALTER TABLE `movie_frame_trackpoints` ADD UNIQUE KEY `uk_movie_frame_label` (`movie_id`, `frame_number`, `label`);

alter table movies add column movie_sha256 varchar(64) after deleted;
drop table movie_data;
UPDATE metadata set v=11 where k='schema_version';

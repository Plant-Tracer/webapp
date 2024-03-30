ALTER TABLE `movies` drop column `center_x`;
ALTER TABLE `movies` drop column `center_y`;
ALTER TABLE `movies` drop column `calib_x`;
ALTER TABLE `movies` drop column `calib_y`;
ALTER TABLE `movies` drop foreign key `movies_usr`;
ALTER TABLE `movies` drop column `calib_user_id`;
ALTER TABLE `movies` drop column `calib_time_t`;
UPDATE metadata set v=6 where k='schema_version';

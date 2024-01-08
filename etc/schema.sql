-- MySQL dump 10.13  Distrib 8.2.0, for macos13 (arm64)
--
-- Host: localhost    Database: pt_local
-- ------------------------------------------------------
-- Server version	8.2.0

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `admins`
--

DROP TABLE IF EXISTS `admins`;
CREATE TABLE `admins` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `course_id` int NOT NULL,
  `mtime` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uc1` (`user_id`,`course_id`),
  KEY `c2` (`course_id`),
  CONSTRAINT `c1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`),
  CONSTRAINT `c2` FOREIGN KEY (`course_id`) REFERENCES `courses` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Table structure for table `api_keys`
--

DROP TABLE IF EXISTS `api_keys`;
CREATE TABLE `api_keys` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `api_key` varchar(255) NOT NULL,
  `first_used_at` int DEFAULT NULL,
  `last_used_at` int DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `use_count` int NOT NULL DEFAULT '0',
  `enabled` int DEFAULT '1',
  `mtime` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `api_keys_ibfk_1` (`user_id`),
  CONSTRAINT `api_keys_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`),
  CONSTRAINT `enabled_chk` CHECK ((`enabled` in (0,1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Table structure for table `courses`
--

DROP TABLE IF EXISTS `courses`;
CREATE TABLE `courses` (
  `id` int NOT NULL AUTO_INCREMENT,
  `course_key` varchar(64) NOT NULL,
  `course_name` varchar(64) DEFAULT NULL,
  `course_section` varchar(64) DEFAULT NULL,
  `max_enrollment` int NOT NULL,
  `mtime` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `course_name` (`course_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Table structure for table `engines`
--

DROP TABLE IF EXISTS `engines`;
CREATE TABLE `engines` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `version` varchar(256) DEFAULT '',
  PRIMARY KEY (`id`),
  UNIQUE KEY `env1` (`name`,`version`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Table structure for table `logs`
--

DROP TABLE IF EXISTS `logs`;
CREATE TABLE `logs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `time_t` int NOT NULL DEFAULT (unix_timestamp()),
  `ipaddr` varchar(39) DEFAULT NULL,
  `apikey_id` int DEFAULT NULL,
  `user_id` int DEFAULT NULL,
  `func_name` varchar(128) DEFAULT NULL,
  `func_args` json DEFAULT NULL,
  `func_return` json DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `apikey_id` (`apikey_id`),
  KEY `user_id` (`user_id`),
  KEY `time_t` (`time_t`),
  KEY `ipaddr` (`ipaddr`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Table structure for table `movie_analysis`
--

DROP TABLE IF EXISTS `movie_analysis`;
CREATE TABLE `movie_analysis` (
  `id` int NOT NULL AUTO_INCREMENT,
  `engine_id` int NOT NULL,
  `annotations` json DEFAULT NULL,
  `movie_id` int NOT NULL,
  PRIMARY KEY (`id`),
  KEY `engine_id` (`engine_id`),
  KEY `mc1` (`movie_id`),
  CONSTRAINT `ma1` FOREIGN KEY (`engine_id`) REFERENCES `engines` (`id`),
  CONSTRAINT `mc1` FOREIGN KEY (`movie_id`) REFERENCES `movies` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Table structure for table `movie_data`
--

DROP TABLE IF EXISTS `movie_data`;
CREATE TABLE `movie_data` (
  `id` int NOT NULL AUTO_INCREMENT,
  `movie_id` int NOT NULL,
  `movie_sha256` varchar(64) DEFAULT NULL,
  `movie_data` mediumblob NOT NULL,
  `mtime` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `movie_id` (`movie_id`),
  CONSTRAINT `ctr1` FOREIGN KEY (`movie_id`) REFERENCES `movies` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Table structure for table `movie_frame_analysis`
--

DROP TABLE IF EXISTS `movie_frame_analysis`;
CREATE TABLE `movie_frame_analysis` (
  `id` int NOT NULL AUTO_INCREMENT,
  `frame_id` int NOT NULL,
  `engine_id` int NOT NULL,
  `annotations` json DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx4` (`frame_id`,`engine_id`),
  KEY `frame_id` (`frame_id`),
  KEY `engine_id` (`engine_id`),
  CONSTRAINT `mfa1` FOREIGN KEY (`frame_id`) REFERENCES `movie_frames` (`id`),
  CONSTRAINT `mfa3` FOREIGN KEY (`engine_id`) REFERENCES `engines` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Table structure for table `movie_frame_trackpoints`
--

DROP TABLE IF EXISTS `movie_frame_trackpoints`;
CREATE TABLE `movie_frame_trackpoints` (
  `id` int NOT NULL AUTO_INCREMENT,
  `frame_id` int NOT NULL,
  `x` int NOT NULL,
  `y` int NOT NULL,
  `label` varchar(255) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk1` (`frame_id`,`label`),
  KEY `frame_id` (`frame_id`),
  CONSTRAINT `movie_frame_trackpoints_ibfk_1` FOREIGN KEY (`frame_id`) REFERENCES `movie_frames` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Table structure for table `movie_frames`
--

DROP TABLE IF EXISTS `movie_frames`;
CREATE TABLE `movie_frames` (
  `id` int NOT NULL AUTO_INCREMENT,
  `movie_id` int NOT NULL,
  `frame_number` int NOT NULL,
  `frame_data` mediumblob,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `mtime` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `frame_sha256` varchar(256) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `i11` (`movie_id`,`frame_number`),
  CONSTRAINT `c10` FOREIGN KEY (`movie_id`) REFERENCES `movies` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Table structure for table `movies`
--

DROP TABLE IF EXISTS `movies`;
CREATE TABLE `movies` (
  `id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(255) NOT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  `created_at` int NOT NULL DEFAULT (unix_timestamp()),
  `user_id` int DEFAULT NULL,
  `course_id` int NOT NULL,
  `published` int DEFAULT '0',
  `deleted` int DEFAULT '0',
  `date_uploaded` int NOT NULL DEFAULT (unix_timestamp()),
  `orig_movie` int DEFAULT NULL,
  `mtime` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `center_x` int DEFAULT NULL,
  `center_y` int DEFAULT NULL,
  `calib_x` float DEFAULT NULL,
  `calib_y` float DEFAULT NULL,
  `calib_user_id` int DEFAULT NULL,
  `calib_time_t` int DEFAULT NULL,
  `fps` decimal(5,2) DEFAULT NULL,
  `width` int DEFAULT NULL,
  `height` int DEFAULT NULL,
  `total_frames` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `deleted` (`deleted`),
  KEY `d2` (`user_id`,`deleted`),
  KEY `title` (`title`),
  KEY `course_id` (`course_id`),
  KEY `movies_usr` (`calib_user_id`),
  FULLTEXT KEY `description` (`description`),
  FULLTEXT KEY `title_ft` (`title`),
  CONSTRAINT `movies_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`),
  CONSTRAINT `movies_ibfk_2` FOREIGN KEY (`course_id`) REFERENCES `courses` (`id`),
  CONSTRAINT `movies_usr` FOREIGN KEY (`calib_user_id`) REFERENCES `users` (`id`),
  CONSTRAINT `movies_chk_1` CHECK ((`deleted` in (0,1))),
  CONSTRAINT `movies_chk_2` CHECK ((`published` in (0,1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Table structure for table `objects`
--

DROP TABLE IF EXISTS `objects`;
CREATE TABLE `objects` (
  `id` int NOT NULL AUTO_INCREMENT,
  `sha256` varchar(64) DEFAULT NULL,
  `mtime` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `data` mediumblob,
  `url` varchar(1024) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `email` varchar(255) NOT NULL,
  `primary_course_id` int NOT NULL,
  `created_at` int NOT NULL DEFAULT (unix_timestamp()),
  `enabled` int DEFAULT '1',
  `links_sent_without_acknowledgement` int NOT NULL DEFAULT '0',
  `mtime` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `demo` int NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`),
  UNIQUE KEY `email` (`email`),
  KEY `c4` (`primary_course_id`),
  CONSTRAINT `c4` FOREIGN KEY (`primary_course_id`) REFERENCES `courses` (`id`),
  CONSTRAINT `users_chk_1` CHECK (((0 <= `enabled`) <= 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;


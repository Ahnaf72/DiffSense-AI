-- phpMyAdmin SQL Dump
-- version 5.2.1
-- https://www.phpmyadmin.net/
--
-- Host: 127.0.0.1
-- Generation Time: Apr 16, 2026 at 02:31 PM
-- Server version: 10.4.32-MariaDB
-- PHP Version: 8.2.12

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Database: `admin_db`
--

-- --------------------------------------------------------

--
-- Table structure for table `reference_pdfs`
--

CREATE TABLE `reference_pdfs` (
  `id` int(11) NOT NULL,
  `filename` varchar(255) DEFAULT NULL,
  `uploaded_by` int(11) DEFAULT NULL,
  `uploaded_at` timestamp NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `reference_pdfs`
--

INSERT INTO `reference_pdfs` (`id`, `filename`, `uploaded_by`, `uploaded_at`) VALUES
(87, 'assignment-cover.pdf', 1, '2026-03-18 12:05:38'),
(89, 'najneensejuti_28132_3004407_CSE499A__Weekly_Report_6.pdf', 1, '2026-03-18 23:21:34'),
(90, 'akhandabiralmahdi_LATE_36688_3011991_CSE499 (1).pdf', 1, '2026-03-18 23:23:13'),
(91, 'barirafiqul_LATE_17606_3011562_All_weekly_reports.pdf', 1, '2026-03-18 23:23:13'),
(92, 'hassankazimahubub_LATE_15903_3008057_2012414045_Kazi Mahbub Hassan_Weekly Report-6.pdf', 1, '2026-03-18 23:23:13'),
(93, 'islamalimul_LATE_17100_3010916_Group-4__Weekly_Report_6__Integrating_NLP_and_LLMs_with_Hyperspectral_Imaging__HSI.pdf', 1, '2026-03-18 23:23:13'),
(94, 'Weekly-Report-1.pdf', 1, '2026-03-19 01:55:28'),
(95, 'source.pdf', 1, '2026-03-19 10:39:43'),
(97, 'admin.pdf', 1, '2026-04-14 19:05:11'),
(98, 'ahmedaqib_LATE_33147_3804799_CSE299_Weekly_Progress_Report 5-1.pdf', 1, '2026-04-15 02:47:34'),
(99, 'dattabadhon_LATE_36955_3804772_Badhon Datta_2222783042_CSE299_Section 3_Week Report 5.docx.pdf', 1, '2026-04-15 02:47:34'),
(100, 'famimfarhanfarooq_LATE_37063_3804664_CSE299_Weekly_report_05.pdf', 1, '2026-04-15 02:47:34'),
(101, 'fardinmdfahim_LATE_41814_3805530_fahimfardin2232842642weeklyreport5-1.pdf', 1, '2026-04-15 02:47:34'),
(102, 'hossainahanafabid_LATE_33080_3805147_CSE299 Report 5.pdf', 1, '2026-04-15 02:47:34'),
(103, 'hossenmgrabbi_LATE_37938_3805050_Weekly_Progress_Report-5.pdf', 1, '2026-04-15 02:47:34'),
(104, 'inannahianislam_LATE_21320_3805462_CSE299_Weekly_Progress_Report5.pdf', 1, '2026-04-15 02:47:34'),
(105, 'islammdminhajul_33398_3799397_CSE299_Weekly_Progress_Report.5.pdf', 1, '2026-04-15 02:47:34'),
(106, 'islamtowhidul_LATE_33693_3805014_CSE299_Weekly_Progress_Report-5.pdf', 1, '2026-04-15 02:47:34'),
(107, 'monkazitazrian_27234_3799469_CSE299_Weekly_Progress_Report by MON-3.pdf', 1, '2026-04-15 02:47:34'),
(108, 'nabilahnaf_LATE_33089_3805150_report 5.pdf', 1, '2026-04-15 02:47:34'),
(109, 'nehanehlanujhath_22736_3799620_CSE299_Weekly_Progress_Report.docx (6).pdf', 1, '2026-04-15 02:47:34'),
(110, 'opinsayedashrafulislam_LATE_41835_3805506_Weekly Report 5.pdf', 1, '2026-04-15 02:47:34'),
(111, 'prietytasmiyaakter_18178_3795327_CSE299_Weekly_Progress_Report_Tasmiya_Shupreety_2021441042_Section_03-1.pdf', 1, '2026-04-15 02:47:34'),
(112, 'raiyanahsanulkarim_LATE_36793_3805508_weekly report (1,2,3,4,5) .pdf', 1, '2026-04-15 02:47:34'),
(113, 'yousuf_LATE_33478_3804912_yousuf weekly report 5.pdf', 1, '2026-04-15 02:47:34'),
(114, 'zitunuribnekawsar_33493_3799418_CSE299_Weekly_Progress_Report-4.pdf', 1, '2026-04-15 02:47:34'),
(115, 'mahmudsamir_33572_3383390_Week 05_Samir Mahmud_2212429042_sec19_spr25.pdf', 1, '2026-04-15 02:49:13'),
(116, 'myeshakazi_LATE_21068_3385344_CSE299_Weekly_Progress_Report05.pdf', 1, '2026-04-15 02:49:13'),
(117, 'myeshakazi_LATE_21068_3385345_CSE299_Weekly_Progress_Report05.docx', 1, '2026-04-15 02:49:13'),
(118, 'taniaafsanaakter_20962_3383396_CSE299.19 Weekly Progress Report 5.pdf', 1, '2026-04-15 02:49:13'),
(119, 'ahmedrazwan_27925_3383401_CSE299_Weekly 5 (razwan)_Progress_Report  4.pdf', 1, '2026-04-15 02:49:13'),
(120, 'arnobazmainiqtidar_33170_3382666_CSE299_Weekly_Progress_Report_5(2211786042).docx', 1, '2026-04-15 02:49:13'),
(121, 'bakshijihan_LATE_33197_3385610_CSE299_Weekly_Report_5 Jihan Bakshi 2211661042 .docx', 1, '2026-04-15 02:49:13'),
(122, 'bhowmikjukta_LATE_19619_3385626_CSE299_Weekly_Progress_Report 5.docx', 1, '2026-04-15 02:49:13'),
(123, 'ishraquefarhan_LATE_33186_3384958_CSE299_Weekly_Progress_Report_Farhan_Ishraque_2212002042-5.docx', 1, '2026-04-15 02:49:13'),
(124, 'islamashraful_35668_3383210_CSE299_Weekly_Progress_Report (2).docx', 1, '2026-04-15 02:49:13'),
(125, 'islamfaijabintay_LATE_17935_3385623_CSE299_Weekly_Progress_Report (5).pdf', 1, '2026-04-15 02:49:13'),
(126, 'islammirtarikul_LATE_24727_3385511_CSE299_Weekly_Progress_Report 1-4 (1).docx', 1, '2026-04-15 02:49:14'),
(127, 'karmakersudipta_LATE_28316_3385197_CSE299_Weekly_Progress_Report Sudipta-1.docx', 1, '2026-04-15 02:49:14'),
(128, 'mamunmohaimenal_37709_3383374_Mohaimen Al Mamun 2221726642 weekly update 05.pdf', 1, '2026-04-15 02:49:14'),
(129, 'mollamdnayeemporag_27352_3383145_week 5 report.pdf', 1, '2026-04-15 02:49:14'),
(130, 'nahidatikulislam_33163_3383226_CSE299_Weekly_Report_-5_(Nahid-2211978042)-1.docx', 1, '2026-04-15 02:49:14'),
(131, 'nayeenahmedzulkar_22370_3383337_Ahmed Zulkar Nayeen 2121592 Weekly update 5.docx', 1, '2026-04-15 02:49:14'),
(132, 'riadjunaedhasan_LATE_33216_3385508_Cse 299 weekly update 55555555.docx', 1, '2026-04-15 02:49:14'),
(133, 'rimanusratjahan_23374_3383333_Nusrat 2122210 Progress 5.docx', 1, '2026-04-15 02:49:14'),
(134, 'roysourav_LATE_22714_3385261_CSE299_Weekly_Progress_Report Sourav-4.docx', 1, '2026-04-15 02:49:14');

-- --------------------------------------------------------

--
-- Table structure for table `users`
--

CREATE TABLE `users` (
  `id` int(11) NOT NULL,
  `username` varchar(50) NOT NULL,
  `full_name` varchar(100) DEFAULT NULL,
  `hashed_password` varchar(255) DEFAULT NULL,
  `role` enum('admin','teacher','student') NOT NULL,
  `disabled` tinyint(1) DEFAULT 0,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `users`
--

INSERT INTO `users` (`id`, `username`, `full_name`, `hashed_password`, `role`, `disabled`, `created_at`) VALUES
(1, 'mainadmin', 'Karima Jaman', '$2b$12$DYTd65NXthwtWQcBUEGhrewDHYNL9m4rjAZDzFM/LPXPSSxyd60Pq', 'admin', 0, '2026-03-11 07:55:37'),
(17, 'hasibul', 'Hasibul Hasan', '$2b$12$fNO4XaQ0vKgVFV/uUh8bzuKBAPp31xMgdqB0.IL/22SdlDpkj0AY6', 'student', 0, '2026-03-16 09:12:16'),
(19, 'mibsam', 'Mibsam Ahmed', '$2b$12$4y4B58b.yAGR/BdhWqV20uhadrxjdJhJcipRROWY2v.JNNgDgWAHq', 'teacher', 0, '2026-03-16 11:10:03'),
(23, 'miku1', 'hzdzhngz', '$2b$12$Yo0YVB4tZRO/MltZiITTLu45M9bLmryKWJRouZnBIhvg/nSygmsG2', 'student', 0, '2026-03-17 14:32:15'),
(24, 'yo', 'hssdxf', '$2b$12$TZfplUEcVwPFUecdJUEg7OymcWAvUzxVwwNpeRtIY7ZeHbkjHXcra', 'teacher', 0, '2026-03-17 15:14:52');

--
-- Indexes for dumped tables
--

--
-- Indexes for table `reference_pdfs`
--
ALTER TABLE `reference_pdfs`
  ADD PRIMARY KEY (`id`),
  ADD KEY `uploaded_by` (`uploaded_by`);

--
-- Indexes for table `users`
--
ALTER TABLE `users`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `username` (`username`);

--
-- AUTO_INCREMENT for dumped tables
--

--
-- AUTO_INCREMENT for table `reference_pdfs`
--
ALTER TABLE `reference_pdfs`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=135;

--
-- AUTO_INCREMENT for table `users`
--
ALTER TABLE `users`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=25;

--
-- Constraints for dumped tables
--

--
-- Constraints for table `reference_pdfs`
--
ALTER TABLE `reference_pdfs`
  ADD CONSTRAINT `reference_pdfs_ibfk_1` FOREIGN KEY (`uploaded_by`) REFERENCES `users` (`id`);
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;

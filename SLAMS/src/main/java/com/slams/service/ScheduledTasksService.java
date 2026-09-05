package com.slams.service;

import com.slams.model.*;
import com.slams.repository.AttendanceRepository;
import com.slams.repository.LeaveBalanceRepository;
import com.slams.repository.UserRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;
import java.util.List;
import java.util.Optional;

@Service
@EnableScheduling
public class ScheduledTasksService {

    private static final Logger logger = LoggerFactory.getLogger(ScheduledTasksService.class);

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private AttendanceRepository attendanceRepository;

    @Autowired
    private LeaveBalanceRepository leaveBalanceRepository;

    // Run Monday to Friday at 8:00 PM (20:00:00)
    @Scheduled(cron = "0 0 20 * * MON-FRI")
    @Transactional
    public void markAutoAbsent() {
        logger.info("[SCHEDULED JOB] Starting Auto-Absent marking job...");
        LocalDate today = LocalDate.now();
        List<User> employees = userRepository.findByRole(Role.ROLE_EMPLOYEE);

        for (User emp : employees) {
            Optional<Attendance> attendance = attendanceRepository.findByUserIdAndDate(emp.getId(), today);
            if (attendance.isEmpty()) {
                Attendance absentRecord = Attendance.builder()
                        .user(emp)
                        .date(today)
                        .status(AttendanceStatus.ABSENT)
                        .workingHours(0.0)
                        .build();
                attendanceRepository.save(absentRecord);
                logger.info("Automatically marked employee '{}' as ABSENT for {}", emp.getUsername(), today);
            }
        }
        logger.info("[SCHEDULED JOB] Auto-Absent marking job completed.");
    }

    // Run at 12:00 AM (midnight) on Jan 1st of every year
    @Scheduled(cron = "0 0 0 1 1 ?")
    @Transactional
    public void carryForwardLeaves() {
        logger.info("[SCHEDULED JOB] Starting Leave Carry-Forward and Reset job...");
        List<LeaveBalance> balances = leaveBalanceRepository.findAll();

        for (LeaveBalance balance : balances) {
            // Earned leaves carried forward, capped at 30 days total (new 18 + carried forward)
            int unusedEarned = balance.getEarnedLeave();
            int newEarned = Math.min(30, 18 + unusedEarned);

            balance.setCasualLeave(12); // Reset Casual leave to 12
            balance.setSickLeave(15);   // Reset Sick leave to 15
            balance.setEarnedLeave(newEarned);

            leaveBalanceRepository.save(balance);
            logger.info("Carried forward leaves for employee '{}': New Earned={}, Casual=12, Sick=15",
                    balance.getUser().getUsername(), newEarned);
        }
        logger.info("[SCHEDULED JOB] Leave Carry-Forward job completed.");
    }
}

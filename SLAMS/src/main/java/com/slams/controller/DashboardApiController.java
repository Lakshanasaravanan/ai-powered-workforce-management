package com.slams.controller;

import com.slams.model.*;
import com.slams.repository.AttendanceRepository;
import com.slams.repository.LeaveRequestRepository;
import com.slams.repository.UserRepository;
import com.slams.service.UserService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDate;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/dashboard")
public class DashboardApiController {

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private AttendanceRepository attendanceRepository;

    @Autowired
    private LeaveRequestRepository leaveRequestRepository;

    @Autowired
    private UserService userService;

    @GetMapping("/stats")
    @PreAuthorize("hasAnyRole('ADMIN', 'MANAGER')")
    public ResponseEntity<Map<String, Object>> getStats(Authentication authentication) {
        User currentUser = userService.findByUsername(authentication.getName())
                .orElseThrow(() -> new RuntimeException("User not found: " + authentication.getName()));

        Map<String, Object> stats = new HashMap<>();
        LocalDate today = LocalDate.now();

        List<User> employees;
        List<Attendance> todayAttendance;
        long pendingLeavesCount;

        if (currentUser.getRole() == Role.ROLE_MANAGER) {
            employees = userRepository.findByReportingManagerAndRole(currentUser, Role.ROLE_EMPLOYEE);
            todayAttendance = employees.isEmpty() ? List.of() : attendanceRepository.findByUserInAndDate(employees, today);
            pendingLeavesCount = employees.isEmpty() ? 0 : leaveRequestRepository.countByUserInAndStatus(employees, LeaveStatus.PENDING);
        } else {
            employees = userRepository.findByRole(Role.ROLE_EMPLOYEE);
            todayAttendance = attendanceRepository.findByDate(today);
            pendingLeavesCount = leaveRequestRepository.countByStatus(LeaveStatus.PENDING);
        }

        long totalEmployees = employees.size();

        long presentCount = todayAttendance.stream().filter(a -> a.getStatus() == AttendanceStatus.PRESENT).count();
        long lateCount = todayAttendance.stream().filter(a -> a.getStatus() == AttendanceStatus.LATE).count();
        long halfDayCount = todayAttendance.stream().filter(a -> a.getStatus() == AttendanceStatus.HALF_DAY).count();
        long absentCount = todayAttendance.stream().filter(a -> a.getStatus() == AttendanceStatus.ABSENT).count();

        long checkedInCount = presentCount + lateCount + halfDayCount;

        double attendancePercentage = 100.0;
        if (totalEmployees > 0) {
            double effectivePresent = presentCount + lateCount + (halfDayCount * 0.5);
            attendancePercentage = Math.round((effectivePresent / totalEmployees) * 100.0 * 100.0) / 100.0;
        }

        stats.put("totalEmployees", totalEmployees);
        stats.put("checkedInCount", checkedInCount);
        stats.put("presentCount", presentCount);
        stats.put("lateCount", lateCount);
        stats.put("halfDayCount", halfDayCount);
        stats.put("absentCount", absentCount);
        stats.put("attendancePercentage", attendancePercentage);
        stats.put("pendingLeavesCount", pendingLeavesCount);

        return ResponseEntity.ok(stats);
    }
}
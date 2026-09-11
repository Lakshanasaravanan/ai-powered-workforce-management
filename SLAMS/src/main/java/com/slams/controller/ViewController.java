package com.slams.controller;

import com.slams.model.*;
import com.slams.dto.AttendanceAnalyticsResponse;
import com.slams.repository.AttendanceRepository;
import com.slams.repository.LeaveRequestRepository;
import com.slams.repository.UserRepository;
import com.slams.service.AttendanceService;
import com.slams.service.LeaveService;
import com.slams.service.UserService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

import java.security.Principal;
import java.time.LocalDate;
import java.util.List;

@Controller
public class ViewController {

    @Autowired
    private UserService userService;

    @Autowired
    private LeaveService leaveService;

    @Autowired
    private AttendanceService attendanceService;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private AttendanceRepository attendanceRepository;

    @Autowired
    private LeaveRequestRepository leaveRequestRepository;

    @GetMapping("/login")
    public String loginPage() {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth != null && auth.isAuthenticated() && !"anonymousUser".equals(auth.getPrincipal())) {
            return "redirect:/";
        }
        return "login";
    }

    @GetMapping({"/", "/dashboard"})
    public String dashboard(Model model, Principal principal) {
        if (principal == null) {
            return "redirect:/login";
        }

        User currentUser = userService.findByUsername(principal.getName())
                .orElseThrow(() -> new RuntimeException("User not found: " + principal.getName()));

        model.addAttribute("currentUser", currentUser);

        if (currentUser.getRole() == Role.ROLE_EMPLOYEE) {
            loadEmployeeDashboard(model, currentUser);
        } else if (currentUser.getRole() == Role.ROLE_HR) {
            loadManagerDashboard(model, currentUser);
        } else if (currentUser.getRole() == Role.ROLE_ADMIN) {
            loadAdminDashboard(model);
        }

        return "dashboard";
    }

    private void loadEmployeeDashboard(Model model, User user) {
        model.addAttribute("todayAttendance",
                attendanceService.getTodayAttendance(user.getUsername()).orElse(null));

        model.addAttribute("leaveBalance",
                leaveService.getLeaveBalance(user.getUsername()));

        model.addAttribute("leaves",
                leaveService.getMyLeaves(user.getUsername()));

        AttendanceAnalyticsResponse analytics = attendanceService.getAttendanceAnalytics(user.getUsername());
        model.addAttribute("attendancePercentage", analytics.attendancePercentage());
        model.addAttribute("presentCount", analytics.presentCount());
        model.addAttribute("lateCount", analytics.lateCount());
        model.addAttribute("halfDayCount", analytics.halfDayCount());
        model.addAttribute("absentCount", analytics.absentCount());
        model.addAttribute("totalDays", analytics.totalDays());
    }

    private void loadManagerDashboard(Model model, User manager) {
        List<User> teamEmployees = userRepository.findByReportingManagerAndRole(manager, Role.ROLE_EMPLOYEE);

        LocalDate today = LocalDate.now();
        List<Attendance> todayAttendance = teamEmployees.isEmpty()
                ? List.of()
                : attendanceRepository.findByUserInAndDate(teamEmployees, today);

        List<LeaveRequest> pendingLeaves = teamEmployees.isEmpty()
                ? List.of()
                : leaveRequestRepository.findByUserInAndStatusOrderByAppliedAtDesc(teamEmployees, LeaveStatus.PENDING);

        long totalEmployees = teamEmployees.size();

        long presentCount = todayAttendance.stream()
                .filter(a -> a.getStatus() == AttendanceStatus.PRESENT)
                .count();

        long lateCount = todayAttendance.stream()
                .filter(a -> a.getStatus() == AttendanceStatus.LATE)
                .count();

        long halfDayCount = todayAttendance.stream()
                .filter(a -> a.getStatus() == AttendanceStatus.HALF_DAY)
                .count();

        long absentCount = todayAttendance.stream()
                .filter(a -> a.getStatus() == AttendanceStatus.ABSENT)
                .count();

        long checkedInCount = presentCount + lateCount + halfDayCount;

        double attendancePercentage = 100.0;
        if (totalEmployees > 0) {
            double effectivePresent = presentCount + lateCount + (halfDayCount * 0.5);
            attendancePercentage = Math.round((effectivePresent / totalEmployees) * 100.0 * 100.0) / 100.0;
        }

        model.addAttribute("pendingLeaves", pendingLeaves);
        model.addAttribute("employees", teamEmployees);

        model.addAttribute("totalEmployees", totalEmployees);
        model.addAttribute("checkedInCount", checkedInCount);
        model.addAttribute("presentCount", presentCount);
        model.addAttribute("lateCount", lateCount);
        model.addAttribute("halfDayCount", halfDayCount);
        model.addAttribute("absentCount", absentCount);
        model.addAttribute("attendancePercentage", attendancePercentage);
        model.addAttribute("pendingLeavesCount", pendingLeaves.size());
        model.addAttribute("todayLogs", todayAttendance);
    }

    private void loadAdminDashboard(Model model) {
        List<User> employees = userService.getEmployees();

        LocalDate today = LocalDate.now();
        List<Attendance> todayAttendance = attendanceRepository.findByDate(today);
        List<LeaveRequest> pendingLeaves = leaveService.getPendingLeaves();

        long totalEmployees = employees.size();

        long presentCount = todayAttendance.stream()
                .filter(a -> a.getStatus() == AttendanceStatus.PRESENT)
                .count();

        long lateCount = todayAttendance.stream()
                .filter(a -> a.getStatus() == AttendanceStatus.LATE)
                .count();

        long halfDayCount = todayAttendance.stream()
                .filter(a -> a.getStatus() == AttendanceStatus.HALF_DAY)
                .count();

        long absentCount = todayAttendance.stream()
                .filter(a -> a.getStatus() == AttendanceStatus.ABSENT)
                .count();

        long checkedInCount = presentCount + lateCount + halfDayCount;

        double attendancePercentage = 100.0;
        if (totalEmployees > 0) {
            double effectivePresent = presentCount + lateCount + (halfDayCount * 0.5);
            attendancePercentage = Math.round((effectivePresent / totalEmployees) * 100.0 * 100.0) / 100.0;
        }

        model.addAttribute("pendingLeaves", pendingLeaves);
        model.addAttribute("employees", employees);

        model.addAttribute("totalEmployees", totalEmployees);
        model.addAttribute("checkedInCount", checkedInCount);
        model.addAttribute("presentCount", presentCount);
        model.addAttribute("lateCount", lateCount);
        model.addAttribute("halfDayCount", halfDayCount);
        model.addAttribute("absentCount", absentCount);
        model.addAttribute("attendancePercentage", attendancePercentage);
        model.addAttribute("pendingLeavesCount", pendingLeaves.size());
        model.addAttribute("todayLogs", todayAttendance);
    }
}

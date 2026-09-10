package com.slams.service;

import com.slams.dto.RegularizationRequest;
import com.slams.dto.AttendanceAnalyticsResponse;
import com.slams.model.*;
import com.slams.repository.AttendanceRegularizationRepository;
import com.slams.repository.AttendanceRepository;
import com.slams.repository.UserRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

@Service
public class AttendanceService {

    @Autowired
    private AttendanceRepository attendanceRepository;
    
    @Autowired
    private AttendanceRegularizationRepository regularizationRepository;

    @Autowired
    private UserRepository userRepository;

    @Value("${slams.attendance.cutoff-time}")
    private String cutoffTimeStr;

    private LocalTime getCutoffTime() {
        return LocalTime.parse(cutoffTimeStr, DateTimeFormatter.ofPattern("HH:mm:ss"));
    }

    @Transactional
    public Attendance checkIn(String username) {
        User user = userRepository.findByUsername(username)
                .orElseThrow(() -> new RuntimeException("User not found: " + username));

        LocalDate today = LocalDate.now();
        Optional<Attendance> existing = attendanceRepository.findByUserIdAndDate(user.getId(), today);

        if (existing.isPresent()) {
            throw new RuntimeException("You have already checked in today at " + existing.get().getCheckInTime());
        }

        LocalTime checkInTime = LocalTime.now();
        LocalTime cutoff = getCutoffTime();
        AttendanceStatus status = checkInTime.isAfter(cutoff) ? AttendanceStatus.LATE : AttendanceStatus.PRESENT;

        Attendance attendance = Attendance.builder()
                .user(user)
                .date(today)
                .checkInTime(checkInTime)
                .status(status)
                .build();

        return attendanceRepository.save(attendance);
    }

    @Transactional
    public Attendance checkOut(String username) {
        User user = userRepository.findByUsername(username)
                .orElseThrow(() -> new RuntimeException("User not found: " + username));

        LocalDate today = LocalDate.now();
        Attendance attendance = attendanceRepository.findByUserIdAndDate(user.getId(), today)
                .orElseThrow(() -> new RuntimeException("Please check in first before checking out."));

        if (attendance.getCheckOutTime() != null) {
            throw new RuntimeException("You have already checked out today at " + attendance.getCheckOutTime());
        }

        LocalTime checkOutTime = LocalTime.now();
        attendance.setCheckOutTime(checkOutTime);

        double minutes = Duration.between(attendance.getCheckInTime(), checkOutTime).toMinutes();
        double hours = Math.round((minutes / 60.0) * 100.0) / 100.0;
        attendance.setWorkingHours(hours);

        if (hours < 4.0) {
            attendance.setStatus(AttendanceStatus.HALF_DAY);
        }

        return attendanceRepository.save(attendance);
    }

    public Optional<Attendance> getTodayAttendance(String username) {
        User user = userRepository.findByUsername(username)
                .orElseThrow(() -> new RuntimeException("User not found: " + username));
        return attendanceRepository.findByUserIdAndDate(user.getId(), LocalDate.now());
    }

    public List<Attendance> getMyAttendance(String username) {
        return attendanceRepository.findByUserUsernameOrderByDateDesc(username);
    }

    public List<Attendance> getTodayAllAttendance() {
        return attendanceRepository.findByDate(LocalDate.now());
    }

    public List<Attendance> getAllAttendance() {
        return attendanceRepository.findAll();
    }

    public AttendanceAnalyticsResponse getAttendanceAnalytics(String username) {
        List<Attendance> list = getMyAttendance(username);

        long total = list.size();
        if (total == 0) {
            return new AttendanceAnalyticsResponse(100.0, 0L, 0L, 0L, 0L, 0L);
        }

        long present = list.stream().filter(a -> a.getStatus() == AttendanceStatus.PRESENT).count();
        long late = list.stream().filter(a -> a.getStatus() == AttendanceStatus.LATE).count();
        long halfDay = list.stream().filter(a -> a.getStatus() == AttendanceStatus.HALF_DAY).count();
        long absent = list.stream().filter(a -> a.getStatus() == AttendanceStatus.ABSENT).count();

        double score = present + late + (halfDay * 0.5);
        double percentage = Math.round((score / total) * 100.0 * 100.0) / 100.0;

        return new AttendanceAnalyticsResponse(percentage, present, late, halfDay, absent, total);
    }

    @Transactional
    public AttendanceRegularization requestRegularization(String username, RegularizationRequest request) {
        User user = userRepository.findByUsername(username)
                .orElseThrow(() -> new RuntimeException("User not found"));

        Attendance attendance = attendanceRepository.findById(request.getAttendanceId())
                .orElseThrow(() -> new RuntimeException("Attendance not found"));

        if (!attendance.getUser().getId().equals(user.getId())) {
            throw new RuntimeException("You can only regularize your own attendance");
        }

        AttendanceRegularization reg = AttendanceRegularization.builder()
                .attendance(attendance)
                .requestedInTime(request.getRequestedInTime())
                .requestedOutTime(request.getRequestedOutTime())
                .reason(request.getReason())
                .status(LeaveStatus.PENDING)
                .build();
        return regularizationRepository.save(reg);
    }

    public List<AttendanceRegularization> getPendingRegularizationsForManager(String managerUsername) {
        User manager = userRepository.findByUsername(managerUsername)
                .orElseThrow(() -> new RuntimeException("Manager not found"));
        // Admin sees all, Manager sees their team
        if (manager.getRole() == Role.ROLE_ADMIN) {
            return regularizationRepository.findAll().stream()
                    .filter(r -> r.getStatus() == LeaveStatus.PENDING).toList();
        }
        return regularizationRepository.findByAttendance_User_ReportingManager_IdAndStatus(manager.getId(), LeaveStatus.PENDING);
    }

    @Transactional
    public void decideRegularization(String managerUsername, Long regularizationId, LeaveStatus decision) {
        User manager = userRepository.findByUsername(managerUsername)
                .orElseThrow(() -> new RuntimeException("Manager not found"));
        
        AttendanceRegularization reg = regularizationRepository.findById(regularizationId)
                .orElseThrow(() -> new RuntimeException("Regularization request not found"));

        reg.setStatus(decision);
        reg.setApprovedBy(manager);

        if (decision == LeaveStatus.APPROVED) {
            Attendance attendance = reg.getAttendance();
            attendance.setCheckInTime(reg.getRequestedInTime());
            if (reg.getRequestedOutTime() != null) {
                attendance.setCheckOutTime(reg.getRequestedOutTime());
                double minutes = Duration.between(attendance.getCheckInTime(), attendance.getCheckOutTime()).toMinutes();
                double hours = Math.round((minutes / 60.0) * 100.0) / 100.0;
                attendance.setWorkingHours(hours);
            }
            attendance.setStatus(AttendanceStatus.PRESENT);
            attendanceRepository.save(attendance);
        }
        regularizationRepository.save(reg);
    }
}

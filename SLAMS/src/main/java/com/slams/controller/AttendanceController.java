package com.slams.controller;

import com.slams.model.Attendance;
import com.slams.service.AttendanceService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.security.Principal;
import java.util.List;

@RestController
@RequestMapping("/api/attendance")
public class AttendanceController {

    @Autowired
    private AttendanceService attendanceService;

    @PostMapping("/checkin")
    @PreAuthorize("hasRole('ROLE_EMPLOYEE')")
    public ResponseEntity<?> checkIn(Principal principal) {
        try {
            Attendance attendance = attendanceService.checkIn(principal.getName());
            return ResponseEntity.ok(attendance);
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(e.getMessage());
        }
    }

    @PutMapping("/checkout")
    @PreAuthorize("hasRole('ROLE_EMPLOYEE')")
    public ResponseEntity<?> checkOut(Principal principal) {
        try {
            Attendance attendance = attendanceService.checkOut(principal.getName());
            return ResponseEntity.ok(attendance);
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(e.getMessage());
        }
    }

    @GetMapping("/today")
    @PreAuthorize("hasRole('ROLE_EMPLOYEE')")
    public ResponseEntity<?> getTodayAttendance(Principal principal) {
        return attendanceService.getTodayAttendance(principal.getName())
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
    }

    @GetMapping("/my")
    @PreAuthorize("hasRole('ROLE_EMPLOYEE')")
    public ResponseEntity<List<Attendance>> getMyAttendance(Principal principal) {
        return ResponseEntity.ok(attendanceService.getMyAttendance(principal.getName()));
    }

    @GetMapping("/analytics")
    public ResponseEntity<?> getAnalytics(Principal principal) {
        return ResponseEntity.ok(attendanceService.getAttendanceAnalytics(principal.getName()));
    }

    @PostMapping("/regularize")
    @PreAuthorize("hasRole('ROLE_EMPLOYEE')")
    public ResponseEntity<?> requestRegularization(Principal principal, @RequestBody com.slams.dto.RegularizationRequest request) {
        try {
            return ResponseEntity.ok(attendanceService.requestRegularization(principal.getName(), request));
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(e.getMessage());
        }
    }

    @GetMapping("/regularize/pending")
    @PreAuthorize("hasRole('ROLE_MANAGER') or hasRole('ROLE_ADMIN')")
    public ResponseEntity<?> getPendingRegularizations(Principal principal) {
        return ResponseEntity.ok(attendanceService.getPendingRegularizationsForManager(principal.getName()));
    }

    @PostMapping("/regularize/{id}/decide")
    @PreAuthorize("hasRole('ROLE_MANAGER') or hasRole('ROLE_ADMIN')")
    public ResponseEntity<?> decideRegularization(Principal principal, @PathVariable Long id, @RequestParam com.slams.model.LeaveStatus status) {
        try {
            attendanceService.decideRegularization(principal.getName(), id, status);
            return ResponseEntity.ok("Successfully " + status);
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(e.getMessage());
        }
    }
}

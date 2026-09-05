package com.slams.controller;

import com.slams.dto.LeaveApplyRequest;
import com.slams.model.LeaveBalance;
import com.slams.model.LeaveRequest;
import com.slams.model.LeaveStatus;
import com.slams.service.LeaveService;
import jakarta.validation.Valid;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.security.Principal;
import java.util.List;

@RestController
@RequestMapping("/api/leaves")
public class LeaveController {

    @Autowired
    private LeaveService leaveService;

    @PostMapping("/apply")
    @PreAuthorize("hasRole('ROLE_EMPLOYEE')")
    public ResponseEntity<?> applyLeave(@Valid @RequestBody LeaveApplyRequest request, Principal principal) {
        try {
            leaveService.applyLeave(
                    principal.getName(),
                    request.getLeaveType(),
                    request.getStartDate(),
                    request.getEndDate(),
                    request.getReason()
            );
            return ResponseEntity.ok().body("{\"message\": \"Leave applied successfully\"}");
        } catch (Exception e) {
            return ResponseEntity.badRequest().body("{\"error\": \"" + e.getMessage() + "\"}");
        }
    }

    @PutMapping("/{id}/status")
    @PreAuthorize("hasAnyRole('ROLE_MANAGER', 'ROLE_ADMIN')")
    public ResponseEntity<?> updateStatus(
            @PathVariable Long id,
            @RequestParam LeaveStatus status,
            @RequestParam(required = false) String rejectionReason,
            Principal principal) {
        try {
            leaveService.updateStatus(id, status, principal.getName(), rejectionReason);
            return ResponseEntity.ok().body("{\"message\": \"Status updated successfully\"}");
        } catch (Exception e) {
            return ResponseEntity.badRequest().body("{\"error\": \"" + e.getMessage() + "\"}");
        }
    }

    @GetMapping("/my")
    @PreAuthorize("hasRole('ROLE_EMPLOYEE')")
    public ResponseEntity<List<LeaveRequest>> getMyLeaves(Principal principal) {
        return ResponseEntity.ok(leaveService.getMyLeaves(principal.getName()));
    }

    @GetMapping("/pending")
    @PreAuthorize("hasAnyRole('ROLE_MANAGER', 'ROLE_ADMIN')")
    public ResponseEntity<List<LeaveRequest>> getPendingLeaves() {
        return ResponseEntity.ok(leaveService.getPendingLeaves());
    }

    @GetMapping("/balance")
    public ResponseEntity<LeaveBalance> getLeaveBalance(Principal principal) {
        return ResponseEntity.ok(leaveService.getLeaveBalance(principal.getName()));
    }
}

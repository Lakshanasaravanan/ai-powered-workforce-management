package com.slams.controller;

import com.slams.dto.LeaveApplyRequest;
import com.slams.dto.LeaveBalanceResponse;
import com.slams.dto.LeaveRequestResponse;
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
    @PreAuthorize("hasRole('EMPLOYEE')")
    public ResponseEntity<?> applyLeave(@Valid @RequestBody LeaveApplyRequest request, Principal principal) {
        leaveService.applyLeave(
                principal.getName(), request.getLeaveType(), request.getStartDate(), request.getEndDate(), request.getReason());
        return ResponseEntity.ok().body(java.util.Map.of("message", "Leave applied successfully"));
    }

    @PutMapping("/{id}/status")
    @PreAuthorize("hasAnyRole('MANAGER', 'ADMIN')")
    public ResponseEntity<?> updateStatus(
            @PathVariable Long id,
            @RequestParam LeaveStatus status,
            @RequestParam(required = false) String rejectionReason,
            Principal principal) {
        leaveService.updateStatus(id, status, principal.getName(), rejectionReason);
        return ResponseEntity.ok().body(java.util.Map.of("message", "Status updated successfully"));
    }

    @GetMapping("/my")
    @PreAuthorize("hasRole('EMPLOYEE')")
    public ResponseEntity<List<LeaveRequestResponse>> getMyLeaves(Principal principal) {
        return ResponseEntity.ok(leaveService.getMyLeaves(principal.getName()).stream().map(LeaveRequestResponse::from).toList());
    }

    @GetMapping("/pending")
    @PreAuthorize("hasAnyRole('MANAGER', 'ADMIN')")
    public ResponseEntity<List<LeaveRequestResponse>> getPendingLeaves() {
        return ResponseEntity.ok(leaveService.getPendingLeaves().stream().map(LeaveRequestResponse::from).toList());
    }

    @GetMapping("/balance")
    @PreAuthorize("hasRole('EMPLOYEE')")
    public ResponseEntity<LeaveBalanceResponse> getLeaveBalance(Principal principal) {
        return ResponseEntity.ok(LeaveBalanceResponse.from(leaveService.getLeaveBalance(principal.getName())));
    }
}

package com.slams.dto;

import com.slams.model.LeaveRequest;

import java.time.LocalDate;
import java.time.LocalDateTime;

public record LeaveRequestResponse(
        Long id, String leaveType, LocalDate startDate, LocalDate endDate,
        String status, LocalDateTime appliedAt, String rejectionReason
) {
    public static LeaveRequestResponse from(LeaveRequest request) {
        return new LeaveRequestResponse(
                request.getId(), request.getLeaveType().name(), request.getStartDate(), request.getEndDate(),
                request.getStatus().name(), request.getAppliedAt(), request.getRejectionReason()
        );
    }
}

package com.slams.dto;

import com.slams.model.LeaveRequest;
import java.time.LocalDate;
import java.time.LocalDateTime;

public record LeaveApplicationResponse(Long leaveRequestId, String status, String leaveType,
        LocalDate startDate, LocalDate endDate, LocalDateTime appliedAt, boolean idempotentReplay) {
    public static LeaveApplicationResponse from(LeaveRequest request, boolean replay) {
        return new LeaveApplicationResponse(request.getId(), request.getStatus().name(), request.getLeaveType().name(),
                request.getStartDate(), request.getEndDate(), request.getAppliedAt(), replay);
    }
}

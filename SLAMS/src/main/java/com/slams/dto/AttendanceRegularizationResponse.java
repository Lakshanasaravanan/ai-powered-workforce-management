package com.slams.dto;

import com.slams.model.AttendanceRegularization;
import java.time.LocalTime;
import java.time.LocalDateTime;

public record AttendanceRegularizationResponse(Long regularizationRequestId, Long attendanceId,
        LocalTime requestedInTime, LocalTime requestedOutTime, String status, LocalDateTime requestedAt, boolean idempotentReplay) {
    public static AttendanceRegularizationResponse from(AttendanceRegularization request, boolean replay) {
        return new AttendanceRegularizationResponse(request.getId(), request.getAttendance().getId(),
                request.getRequestedInTime(), request.getRequestedOutTime(), request.getStatus().name(), request.getRequestedAt(), replay);
    }
}

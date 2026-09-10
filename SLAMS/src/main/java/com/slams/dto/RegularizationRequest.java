package com.slams.dto;

import lombok.Data;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.time.LocalTime;

@Data
public class RegularizationRequest {
    @NotNull(message = "Attendance ID is required") private Long attendanceId;
    @NotNull(message = "Requested in time is required") private LocalTime requestedInTime;
    private LocalTime requestedOutTime;
    @NotBlank(message = "Reason is required") @Size(max = 500, message = "Reason must not exceed 500 characters") private String reason;
}

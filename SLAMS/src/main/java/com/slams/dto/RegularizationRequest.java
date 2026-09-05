package com.slams.dto;

import lombok.Data;
import java.time.LocalTime;

@Data
public class RegularizationRequest {
    private Long attendanceId;
    private LocalTime requestedInTime;
    private LocalTime requestedOutTime;
    private String reason;
}

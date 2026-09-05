package com.slams.dto;

import com.slams.model.RequestDurationType;
import com.slams.model.WorkMode;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

import java.time.LocalDate;

@Data
public class WorkModeRequestDto {

    @NotNull(message = "Requested work mode is required")
    private WorkMode requestedMode;

    @NotNull(message = "Duration type is required")
    private RequestDurationType durationType;

    private LocalDate startDate;
    private LocalDate endDate;

    @NotBlank(message = "Reason is required")
    private String reason;
}
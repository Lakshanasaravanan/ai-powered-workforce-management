package com.slams.dto;

import com.slams.model.ApprovalStatus;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

@Data
public class WorkModeDecisionDto {

    @NotNull(message = "Decision status is required")
    private ApprovalStatus status; // APPROVED or REJECTED

    private String managerRemarks;
}
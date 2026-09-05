package com.slams.dto;

import com.slams.model.Role;
import com.slams.model.User;
import com.slams.model.UserStatus;
import com.slams.model.WorkMode;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDate;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class EmployeeResponse {

    private Long id;
    private String employeeId;
    private String fullName;
    private String username;
    private String email;
    private String designation;
    private String phoneNumber;
    private LocalDate joiningDate;
    private Role role;
    private UserStatus status;
    private WorkMode workMode;

    private Long departmentId;
    private String departmentName;

    private Long reportingManagerId;
    private String reportingManagerName;

    private Long shiftId;
    private String shiftName;

    public static EmployeeResponse from(User user) {
        return new EmployeeResponse(
                user.getId(),
                user.getEmployeeId(),
                user.getFullName(),
                user.getUsername(),
                user.getEmail(),
                user.getDesignation(),
                user.getPhoneNumber(),
                user.getJoiningDate(),
                user.getRole(),
                user.getStatus(),
                user.getWorkMode(),

                user.getDepartment() != null ? user.getDepartment().getId() : null,
                user.getDepartment() != null ? user.getDepartment().getName() : null,

                user.getReportingManager() != null ? user.getReportingManager().getId() : null,
                user.getReportingManager() != null ? user.getReportingManager().getFullName() : null,

                user.getShift() != null ? user.getShift().getId() : null,
                user.getShift() != null ? user.getShift().getName() : null
        );
    }
}
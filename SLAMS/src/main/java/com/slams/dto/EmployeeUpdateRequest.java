package com.slams.dto;

import com.slams.model.Role;
import com.slams.model.UserStatus;
import com.slams.model.WorkMode;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDate;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class EmployeeUpdateRequest {

    @Size(min = 3, max = 50, message = "Username must be between 3 and 50 characters")
    private String username;

    @Size(min = 6, max = 100, message = "Password must be at least 6 characters")
    private String password;

    @Email(message = "Email should be valid")
    private String email;

    private String fullName;
    private String employeeId;
    private String designation;
    private String phoneNumber;
    private LocalDate joiningDate;
    private Role role;
    private UserStatus status;
    private WorkMode workMode;
    private Long departmentId;
    private Long reportingManagerId;
    private Long shiftId;
}
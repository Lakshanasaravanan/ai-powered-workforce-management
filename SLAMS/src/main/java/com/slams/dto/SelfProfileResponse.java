package com.slams.dto;

import com.slams.model.User;

public record SelfProfileResponse(
        String employeeId,
        String username,
        String fullName,
        String email,
        String department,
        String designation,
        String role
) {
    public static SelfProfileResponse from(User user) {
        return new SelfProfileResponse(
                user.getEmployeeId(), user.getUsername(), user.getFullName(), user.getEmail(),
                user.getDepartment() == null ? null : user.getDepartment().getName(),
                user.getDesignation(), user.getRole().name()
        );
    }
}

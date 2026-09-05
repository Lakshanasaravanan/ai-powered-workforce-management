package com.slams.dto;

import com.slams.model.Department;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class DepartmentResponse {

    private Long id;
    private String code;
    private String name;
    private String description;
    private Boolean active;

    private Long managerId;
    private String managerName;

    public static DepartmentResponse from(Department department) {
        return new DepartmentResponse(
                department.getId(),
                department.getCode(),
                department.getName(),
                department.getDescription(),
                department.getActive(),
                department.getManager() != null ? department.getManager().getId() : null,
                department.getManager() != null ? department.getManager().getFullName() : null
        );
    }
}
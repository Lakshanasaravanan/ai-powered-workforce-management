package com.slams.dto;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class DepartmentUpdateRequest {
    private String code;
    private String name;
    private String description;
    private Long managerId;
    private Boolean active;
}
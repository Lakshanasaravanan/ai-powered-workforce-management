package com.slams.controller;

import com.slams.dto.DepartmentCreateRequest;
import com.slams.dto.DepartmentResponse;
import com.slams.dto.DepartmentUpdateRequest;
import com.slams.dto.EmployeeCreateRequest;
import com.slams.dto.EmployeeResponse;
import com.slams.dto.EmployeeUpdateRequest;
import com.slams.model.Department;
import com.slams.model.User;
import com.slams.repository.DepartmentRepository;
import com.slams.repository.UserRepository;
import com.slams.service.UserService;
import jakarta.validation.Valid;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/admin")
public class AdminController {

    @Autowired
    private UserService userService;

    @Autowired
    private DepartmentRepository departmentRepository;

    @Autowired
    private UserRepository userRepository;

    // =========================================================
    // Employee Management APIs
    // =========================================================

    @GetMapping("/employees")
    public ResponseEntity<List<EmployeeResponse>> getAllEmployees() {
        List<EmployeeResponse> employees = userService.getAllUsers()
                .stream()
                .map(EmployeeResponse::from)
                .toList();

        return ResponseEntity.ok(employees);
    }

    @GetMapping("/employees/active")
    public ResponseEntity<List<EmployeeResponse>> getActiveEmployees() {
        List<EmployeeResponse> employees = userService.getActiveEmployees()
                .stream()
                .map(EmployeeResponse::from)
                .toList();

        return ResponseEntity.ok(employees);
    }

    @GetMapping("/managers")
    public ResponseEntity<List<EmployeeResponse>> getManagers() {
        List<EmployeeResponse> managers = userService.getManagers()
                .stream()
                .map(EmployeeResponse::from)
                .toList();

        return ResponseEntity.ok(managers);
    }

    @PostMapping("/employees")
    public ResponseEntity<?> createEmployee(@Valid @RequestBody EmployeeCreateRequest request) {
        try {
            User user = userService.createUser(
                    request.getUsername(),
                    request.getPassword(),
                    request.getEmail(),
                    request.getFullName(),
                    request.getRole(),
                    request.getEmployeeId(),
                    request.getDesignation(),
                    request.getPhoneNumber(),
                    request.getJoiningDate(),
                    request.getDepartmentId(),
                    request.getReportingManagerId(),
                    request.getShiftId(),
                    request.getWorkMode(),
                    request.getStatus()
            );

            return ResponseEntity.ok(Map.of(
                    "message", "Employee created successfully",
                    "userId", user.getId(),
                    "employeeId", user.getEmployeeId()
            ));
        } catch (RuntimeException ex) {
            return ResponseEntity.badRequest().body(Map.of("error", ex.getMessage()));
        }
    }

    @PutMapping("/employees/{id}")
    public ResponseEntity<?> updateEmployee(@PathVariable Long id,
                                            @Valid @RequestBody EmployeeUpdateRequest request) {
        try {
            User user = userService.updateUser(
                    id,
                    request.getUsername(),
                    request.getPassword(),
                    request.getEmail(),
                    request.getFullName(),
                    request.getRole(),
                    request.getEmployeeId(),
                    request.getDesignation(),
                    request.getPhoneNumber(),
                    request.getJoiningDate(),
                    request.getDepartmentId(),
                    request.getReportingManagerId(),
                    request.getShiftId(),
                    request.getWorkMode(),
                    request.getStatus()
            );

            return ResponseEntity.ok(Map.of(
                    "message", "Employee updated successfully",
                    "userId", user.getId(),
                    "employeeId", user.getEmployeeId()
            ));
        } catch (RuntimeException ex) {
            return ResponseEntity.badRequest().body(Map.of("error", ex.getMessage()));
        }
    }

    @PatchMapping("/employees/{id}/deactivate")
    public ResponseEntity<?> deactivateEmployee(@PathVariable Long id) {
        try {
            User user = userService.deactivateUser(id);
            return ResponseEntity.ok(Map.of(
                    "message", "Employee deactivated successfully",
                    "userId", user.getId(),
                    "status", user.getStatus().name()
            ));
        } catch (RuntimeException ex) {
            return ResponseEntity.badRequest().body(Map.of("error", ex.getMessage()));
        }
    }

    @PatchMapping("/employees/{id}/reactivate")
    public ResponseEntity<?> reactivateEmployee(@PathVariable Long id) {
        try {
            User user = userService.reactivateUser(id);
            return ResponseEntity.ok(Map.of(
                    "message", "Employee reactivated successfully",
                    "userId", user.getId(),
                    "status", user.getStatus().name()
            ));
        } catch (RuntimeException ex) {
            return ResponseEntity.badRequest().body(Map.of("error", ex.getMessage()));
        }
    }

    // =========================================================
    // Department Management APIs
    // =========================================================

    @GetMapping("/departments")
    public ResponseEntity<List<DepartmentResponse>> getAllDepartments() {
        List<DepartmentResponse> departments = departmentRepository.findAll()
                .stream()
                .map(DepartmentResponse::from)
                .toList();

        return ResponseEntity.ok(departments);
    }

    @GetMapping("/departments/active")
    public ResponseEntity<List<DepartmentResponse>> getActiveDepartments() {
        List<DepartmentResponse> departments = departmentRepository.findByActiveTrue()
                .stream()
                .map(DepartmentResponse::from)
                .toList();

        return ResponseEntity.ok(departments);
    }

    @PostMapping("/departments")
    public ResponseEntity<?> createDepartment(@Valid @RequestBody DepartmentCreateRequest request) {
        try {
            if (departmentRepository.existsByCode(request.getCode())) {
                return ResponseEntity.badRequest().body(Map.of("error", "Department code already exists"));
            }

            if (departmentRepository.existsByName(request.getName())) {
                return ResponseEntity.badRequest().body(Map.of("error", "Department name already exists"));
            }

            User manager = null;
            if (request.getManagerId() != null) {
                manager = userRepository.findById(request.getManagerId())
                        .orElseThrow(() -> new RuntimeException("Manager not found with id: " + request.getManagerId()));
            }

            Department department = Department.builder()
                    .code(request.getCode())
                    .name(request.getName())
                    .description(request.getDescription())
                    .manager(manager)
                    .active(true)
                    .build();

            Department saved = departmentRepository.save(department);

            return ResponseEntity.ok(Map.of(
                    "message", "Department created successfully",
                    "departmentId", saved.getId(),
                    "departmentCode", saved.getCode()
            ));
        } catch (RuntimeException ex) {
            return ResponseEntity.badRequest().body(Map.of("error", ex.getMessage()));
        }
    }

    @PutMapping("/departments/{id}")
    public ResponseEntity<?> updateDepartment(@PathVariable Long id,
                                              @RequestBody DepartmentUpdateRequest request) {
        try {
            Department department = departmentRepository.findById(id)
                    .orElseThrow(() -> new RuntimeException("Department not found with id: " + id));

            if (request.getCode() != null && !request.getCode().isBlank()) {
                departmentRepository.findByCode(request.getCode()).ifPresent(existing -> {
                    if (!existing.getId().equals(id)) {
                        throw new RuntimeException("Department code already exists");
                    }
                });
                department.setCode(request.getCode());
            }

            if (request.getName() != null && !request.getName().isBlank()) {
                departmentRepository.findByName(request.getName()).ifPresent(existing -> {
                    if (!existing.getId().equals(id)) {
                        throw new RuntimeException("Department name already exists");
                    }
                });
                department.setName(request.getName());
            }

            if (request.getDescription() != null) {
                department.setDescription(request.getDescription());
            }

            if (request.getActive() != null) {
                department.setActive(request.getActive());
            }

            if (request.getManagerId() != null) {
                User manager = userRepository.findById(request.getManagerId())
                        .orElseThrow(() -> new RuntimeException("Manager not found with id: " + request.getManagerId()));
                department.setManager(manager);
            }

            Department updated = departmentRepository.save(department);

            return ResponseEntity.ok(Map.of(
                    "message", "Department updated successfully",
                    "departmentId", updated.getId(),
                    "departmentCode", updated.getCode()
            ));
        } catch (RuntimeException ex) {
            return ResponseEntity.badRequest().body(Map.of("error", ex.getMessage()));
        }
    }
}
package com.slams.controller;

import com.slams.dto.SelfProfileResponse;
import com.slams.exception.ResourceNotFoundException;
import com.slams.model.User;
import com.slams.service.UserService;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.security.Principal;

@RestController
@RequestMapping("/api/employees")
public class EmployeeController {
    private final UserService userService;

    public EmployeeController(UserService userService) {
        this.userService = userService;
    }

    @GetMapping("/me")
    @PreAuthorize("hasRole('EMPLOYEE')")
    public ResponseEntity<SelfProfileResponse> getMyProfile(Principal principal) {
        User user = userService.findByUsername(principal.getName())
                .orElseThrow(() -> new ResourceNotFoundException("Employee profile is unavailable"));
        return ResponseEntity.ok(SelfProfileResponse.from(user));
    }
}

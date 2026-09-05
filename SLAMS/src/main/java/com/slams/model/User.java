package com.slams.model;

import jakarta.persistence.*;
import lombok.*;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;

import java.time.LocalDate;
import java.util.Collection;
import java.util.List;

@Entity
@Table(name = "users")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
@ToString(exclude = {"department", "shift", "reportingManager"})
@EqualsAndHashCode(onlyExplicitlyIncluded = true)
public class User implements UserDetails {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @EqualsAndHashCode.Include
    private Long id;

    @Column(unique = true, nullable = false, length = 50)
    private String username;

    @Column(nullable = false)
    private String password;

    @Column(unique = true, nullable = false, length = 100)
    private String email;

    @Column(nullable = false, length = 100)
    private String fullName;

    /**
     * Employee code used by organization / HR / admin.
     * Example: EMP001, SLAMS102, etc.
     */
    @Column(unique = true, length = 30)
    private String employeeId;

    /**
     * Designation / Job title of the employee.
     * Example: Software Engineer, HR Executive, Team Lead
     */
    @Column(length = 100)
    private String designation;

    /**
     * Contact number of employee.
     */
    @Column(length = 20)
    private String phoneNumber;

    /**
     * Date of joining the organization.
     */
    private LocalDate joiningDate;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private Role role;

    /**
     * Employment / account status.
     * ACTIVE, PROBATION, NOTICE_PERIOD, RESIGNED, TERMINATED, etc.
     */
    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    @Builder.Default
    private UserStatus status = UserStatus.ACTIVE;

    /**
     * Work mode for attendance reference.
     * WFO / WFH / HYBRID
     */
    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    @Builder.Default
    private WorkMode workMode = WorkMode.WFO;

    /**
     * Employee's department
     */
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "department_id")
    private Department department;

    /**
     * Assigned shift for attendance timing
     */
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "shift_id")
    private Shift shift;

    /**
     * Reporting manager / approver
     */
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "reporting_manager_id")
    private User reportingManager;

    // =========================
    // Spring Security Methods
    // =========================

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return List.of(new SimpleGrantedAuthority(role.name()));
    }

    /**
     * If employee is resigned or terminated, account should not be considered active for login.
     */
    @Override
    public boolean isAccountNonExpired() {
        return status != UserStatus.TERMINATED && status != UserStatus.RESIGNED;
    }

    @Override
    public boolean isAccountNonLocked() {
        return true;
    }

    @Override
    public boolean isCredentialsNonExpired() {
        return true;
    }

    /**
     * Login enabled only for employees who are still valid in the organization.
     */
    @Override
    public boolean isEnabled() {
        return status == UserStatus.ACTIVE
                || status == UserStatus.PROBATION
                || status == UserStatus.NOTICE_PERIOD;
    }
}
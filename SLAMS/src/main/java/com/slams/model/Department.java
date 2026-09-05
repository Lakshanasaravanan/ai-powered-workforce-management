package com.slams.model;

import jakarta.persistence.*;
import lombok.*;

import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "departments")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
@ToString(exclude = {"manager", "employees"})
@EqualsAndHashCode(onlyExplicitlyIncluded = true)
public class Department {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @EqualsAndHashCode.Include
    private Long id;

    /**
     * Department code used internally by admin/HR.
     * Example: HR, IT, FIN, OPS
     */
    @Column(unique = true, nullable = false, length = 20)
    private String code;

    /**
     * Department display name.
     * Example: Human Resources, Information Technology
     */
    @Column(unique = true, nullable = false, length = 100)
    private String name;

    /**
     * Optional department description.
     */
    @Column(length = 255)
    private String description;

    /**
     * Department active/inactive state.
     * Better than deleting departments directly.
     */
    @Builder.Default
    @Column(nullable = false)
    private Boolean active = true;

    /**
     * Department manager / department head.
     */
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "manager_id")
    private User manager;

    /**
     * Employees mapped to this department.
     * User entity already has: private Department department;
     */
    @OneToMany(mappedBy = "department")
    @Builder.Default
    private List<User> employees = new ArrayList<>();
}
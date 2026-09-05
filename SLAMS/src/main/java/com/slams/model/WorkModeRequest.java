package com.slams.model;

import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDate;
import java.time.LocalDateTime;

@Entity
@Table(name = "work_mode_requests")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class WorkModeRequest {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /**
     * Employee who requested work mode change
     */
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "employee_id", nullable = false)
    private User employee;

    /**
     * Requested mode: WFO / WFH / HYBRID
     */
    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private WorkMode requestedMode;

    /**
     * TEMPORARY or PERMANENT
     */
    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private RequestDurationType durationType;

    /**
     * Used only for temporary requests.
     * For permanent requests these can be null.
     */
    private LocalDate startDate;
    private LocalDate endDate;

    /**
     * Why employee is requesting this mode
     */
    @Column(nullable = false, length = 500)
    private String reason;

    /**
     * PENDING / APPROVED / REJECTED / CANCELLED
     */
    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private ApprovalStatus status;

    /**
     * Optional comments from manager/admin
     */
    @Column(length = 500)
    private String managerRemarks;

    /**
     * When employee submitted request
     */
    @Column(nullable = false)
    private LocalDateTime requestedAt;

    /**
     * When manager/admin approved or rejected
     */
    private LocalDateTime decidedAt;

    /**
     * Manager/Admin who approved/rejected this request
     */
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "approved_by")
    private User approvedBy;
}
package com.slams.service;

import com.slams.model.*;
import com.slams.exception.BusinessRuleConflictException;
import com.slams.exception.MutationRequestValidationException;
import com.slams.exception.ResourceNotFoundException;
import com.slams.repository.LeaveBalanceRepository;
import com.slams.repository.LeaveRequestRepository;
import com.slams.repository.UserRepository;
import com.slams.dto.LeaveApplyRequest;
import com.slams.dto.LeaveApplicationResponse;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;

@Service
public class LeaveService {

    @Autowired
    private LeaveRequestRepository leaveRequestRepository;

    @Autowired
    private LeaveBalanceRepository leaveBalanceRepository;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private EmailService emailService;
    @Autowired
    private IdempotencyService idempotencyService;

    public int calculateWorkingDays(LocalDate start, LocalDate end) {
        int workingDays = 0;
        LocalDate current = start;
        while (!current.isAfter(end)) {
            // Exclude Saturday (6) and Sunday (7)
            int dayOfWeek = current.getDayOfWeek().getValue();
            if (dayOfWeek < 6) {
                workingDays++;
            }
            current = current.plusDays(1);
        }
        return workingDays;
    }

    @Transactional
    public LeaveApplicationResponse applyLeave(String username, String idempotencyKey, LeaveApplyRequest input) {
        validateIdempotencyKey(idempotencyKey);
        User user = userRepository.findByUsername(username).orElseThrow(() -> new ResourceNotFoundException("Employee is unavailable"));
        String hash = PayloadHasher.sha256(input.getLeaveType().name() + "|" + input.getStartDate() + "|" + input.getEndDate() + "|" + input.getReason());
        var result = idempotencyService.execute(idempotencyKey, user, "LEAVE_APPLY", hash, LeaveApplicationResponse.class,
                () -> LeaveApplicationResponse.from(createLeave(user, input.getLeaveType(), input.getStartDate(), input.getEndDate(), input.getReason()), false));
        LeaveApplicationResponse response = result.body();
        return new LeaveApplicationResponse(response.leaveRequestId(), response.status(), response.leaveType(), response.startDate(),
                response.endDate(), response.appliedAt(), result.replay());
    }

    private LeaveRequest createLeave(User user, LeaveType leaveType, LocalDate startDate, LocalDate endDate, String reason) {
        if (startDate.isAfter(endDate)) {
            throw new BusinessRuleConflictException("INVALID_LEAVE_DATE_RANGE", "Start date cannot be after end date.");
        }
        if (startDate.isBefore(LocalDate.now())) {
            throw new BusinessRuleConflictException("INVALID_LEAVE_DATE_RANGE", "Cannot apply leave for past dates.");
        }

        int duration = calculateWorkingDays(startDate, endDate);
        if (duration == 0) {
            throw new BusinessRuleConflictException("LEAVE_WEEKEND_ONLY", "Cannot apply leave for weekends only.");
        }

        LeaveBalance balance = leaveBalanceRepository.findByUserId(user.getId())
                .orElseThrow(() -> new ResourceNotFoundException("Leave balance is unavailable"));

        if (leaveRequestRepository.existsByUserIdAndStatusInAndStartDateLessThanEqualAndEndDateGreaterThanEqual(
                user.getId(), List.of(LeaveStatus.PENDING, LeaveStatus.APPROVED), endDate, startDate)) {
            throw new BusinessRuleConflictException("LEAVE_OVERLAP", "An overlapping leave request already exists");
        }

        // Validate leave balance
        int currentBalance = getBalanceForType(balance, leaveType);
        if (currentBalance < duration) {
            throw new BusinessRuleConflictException("INSUFFICIENT_LEAVE_BALANCE", "Insufficient leave balance");
        }

        LeaveRequest request = LeaveRequest.builder()
                .user(user)
                .leaveType(leaveType)
                .startDate(startDate)
                .endDate(endDate)
                .status(LeaveStatus.PENDING)
                .reason(reason)
                .appliedAt(LocalDateTime.now())
                .build();

        return leaveRequestRepository.save(request);
    }

    private static void validateIdempotencyKey(String key) {
        if (key == null || key.length() > 64) throw new MutationRequestValidationException("IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key is required");
        try { java.util.UUID.fromString(key); } catch (IllegalArgumentException exception) { throw new MutationRequestValidationException("IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key must be a UUID"); }
    }

    @Transactional
    public LeaveRequest updateStatus(Long requestId, LeaveStatus status, String managerUsername, String rejectionReason) {
        LeaveRequest request = leaveRequestRepository.findById(requestId)
                .orElseThrow(() -> new ResourceNotFoundException("Leave request is unavailable"));

        if (request.getStatus() != LeaveStatus.PENDING) {
            throw new BusinessRuleConflictException("INVALID_ACTION_STATE", "Only pending leave requests can be updated");
        }

        User manager = userRepository.findByUsername(managerUsername)
                .orElseThrow(() -> new ResourceNotFoundException("Manager is unavailable"));

        request.setStatus(status);
        request.setApprovedBy(manager.getFullName());
        
        if (status == LeaveStatus.APPROVED) {
            LeaveBalance balance = leaveBalanceRepository.findByUserId(request.getUser().getId())
                    .orElseThrow(() -> new ResourceNotFoundException("Leave balance is unavailable"));

            int duration = calculateWorkingDays(request.getStartDate(), request.getEndDate());
            if (getBalanceForType(balance, request.getLeaveType()) < duration) {
                throw new BusinessRuleConflictException("INSUFFICIENT_LEAVE_BALANCE", "Insufficient leave balance at approval time");
            }
            // Pessimistically locked balance row is rechecked before deduction.
            deductLeaves(balance, request.getLeaveType(), duration);
            leaveBalanceRepository.save(balance);
        } else if (status == LeaveStatus.REJECTED) {
            request.setRejectionReason(rejectionReason);
        }

        LeaveRequest savedRequest = leaveRequestRepository.save(request);

        // Notify user via simulated email
        String subject = "Leave Application " + status.name();
        String body = String.format("Dear %s,\n\nYour application for %s leave starting on %s and ending on %s has been %s by %s.%s\n\nBest regards,\nHR Department",
                request.getUser().getFullName(),
                request.getLeaveType().name(),
                request.getStartDate().toString(),
                request.getEndDate().toString(),
                status.name(),
                manager.getFullName(),
                status == LeaveStatus.REJECTED ? "\nReason for rejection: " + rejectionReason : "");

        emailService.sendEmail(request.getUser().getEmail(), subject, body);

        return savedRequest;
    }

    public List<LeaveRequest> getMyLeaves(String username) {
        return leaveRequestRepository.findByUserUsernameOrderByAppliedAtDesc(username);
    }

    public List<LeaveRequest> getPendingLeaves() {
        return leaveRequestRepository.findByStatusOrderByAppliedAtDesc(LeaveStatus.PENDING);
    }

    public List<LeaveRequest> getAllLeaves() {
        return leaveRequestRepository.findAll();
    }

    public LeaveBalance getLeaveBalance(String username) {
        return leaveBalanceRepository.findByUserUsername(username)
                .orElseThrow(() -> new ResourceNotFoundException("Leave balance is unavailable"));
    }

    private int getBalanceForType(LeaveBalance balance, LeaveType type) {
        return switch (type) {
            case CASUAL -> balance.getCasualLeave();
            case SICK -> balance.getSickLeave();
            case EARNED -> balance.getEarnedLeave();
        };
    }

    private void deductLeaves(LeaveBalance balance, LeaveType type, int days) {
        switch (type) {
            case CASUAL -> balance.setCasualLeave(balance.getCasualLeave() - days);
            case SICK -> balance.setSickLeave(balance.getSickLeave() - days);
            case EARNED -> balance.setEarnedLeave(balance.getEarnedLeave() - days);
        }
    }
}

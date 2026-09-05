package com.slams.service;

import com.slams.model.*;
import com.slams.repository.LeaveBalanceRepository;
import com.slams.repository.LeaveRequestRepository;
import com.slams.repository.UserRepository;
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
    public LeaveRequest applyLeave(String username, LeaveType leaveType, LocalDate startDate, LocalDate endDate, String reason) {
        if (startDate.isAfter(endDate)) {
            throw new RuntimeException("Start date cannot be after end date.");
        }
        if (startDate.isBefore(LocalDate.now())) {
            throw new RuntimeException("Cannot apply leave for past dates.");
        }

        User user = userRepository.findByUsername(username)
                .orElseThrow(() -> new RuntimeException("User not found: " + username));

        int duration = calculateWorkingDays(startDate, endDate);
        if (duration == 0) {
            throw new RuntimeException("Cannot apply leave for weekends only.");
        }

        LeaveBalance balance = leaveBalanceRepository.findByUserId(user.getId())
                .orElseThrow(() -> new RuntimeException("Leave balance record not found for user: " + username));

        // Validate leave balance
        int currentBalance = getBalanceForType(balance, leaveType);
        if (currentBalance < duration) {
            throw new RuntimeException("Insufficient " + leaveType + " leave balance. Required: " + duration + ", Available: " + currentBalance);
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

    @Transactional
    public LeaveRequest updateStatus(Long requestId, LeaveStatus status, String managerUsername, String rejectionReason) {
        LeaveRequest request = leaveRequestRepository.findById(requestId)
                .orElseThrow(() -> new RuntimeException("Leave request not found with ID: " + requestId));

        if (request.getStatus() != LeaveStatus.PENDING) {
            throw new RuntimeException("Can only approve or reject pending leave requests.");
        }

        User manager = userRepository.findByUsername(managerUsername)
                .orElseThrow(() -> new RuntimeException("Manager not found: " + managerUsername));

        request.setStatus(status);
        request.setApprovedBy(manager.getFullName());
        
        if (status == LeaveStatus.APPROVED) {
            int duration = calculateWorkingDays(request.getStartDate(), request.getEndDate());
            LeaveBalance balance = leaveBalanceRepository.findByUserId(request.getUser().getId())
                    .orElseThrow(() -> new RuntimeException("Leave balance record not found."));

            // Deduct the leaves from the balance
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
                .orElseThrow(() -> new RuntimeException("Leave balance not found for: " + username));
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

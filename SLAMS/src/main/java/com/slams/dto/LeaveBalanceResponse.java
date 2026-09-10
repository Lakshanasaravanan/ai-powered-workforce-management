package com.slams.dto;

import com.slams.model.LeaveBalance;

public record LeaveBalanceResponse(int casualLeave, int sickLeave, int earnedLeave) {
    public static LeaveBalanceResponse from(LeaveBalance balance) {
        return new LeaveBalanceResponse(balance.getCasualLeave(), balance.getSickLeave(), balance.getEarnedLeave());
    }
}

package com.slams.dto;

public record AttendanceAnalyticsResponse(
        double attendancePercentage, long presentCount, long lateCount,
        long halfDayCount, long absentCount, long totalDays
) {
}

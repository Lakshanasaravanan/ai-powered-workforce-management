package com.slams.dto;

import com.slams.model.Attendance;

import java.time.LocalDate;
import java.time.LocalTime;

public record AttendanceResponse(
        Long id, LocalDate date, LocalTime checkInTime, LocalTime checkOutTime,
        String status, Double workingHours
) {
    public static AttendanceResponse from(Attendance attendance) {
        return new AttendanceResponse(
                attendance.getId(), attendance.getDate(), attendance.getCheckInTime(), attendance.getCheckOutTime(),
                attendance.getStatus().name(), attendance.getWorkingHours()
        );
    }
}

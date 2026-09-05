package com.slams.repository;

import com.slams.model.AttendanceRegularization;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface AttendanceRegularizationRepository extends JpaRepository<AttendanceRegularization, Long> {
    List<AttendanceRegularization> findByAttendance_User_ReportingManager_IdAndStatus(Long managerId, com.slams.model.LeaveStatus status);
    List<AttendanceRegularization> findByAttendance_UserId(Long userId);
}

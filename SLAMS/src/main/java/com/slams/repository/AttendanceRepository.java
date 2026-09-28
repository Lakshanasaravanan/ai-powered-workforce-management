package com.slams.repository;

import com.slams.model.Attendance;
import com.slams.model.AttendanceStatus;
import com.slams.model.User;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;
import org.springframework.data.jpa.repository.Lock;
import jakarta.persistence.LockModeType;

import java.time.LocalDate;
import java.util.Collection;
import java.util.List;
import java.util.Optional;

@Repository
public interface AttendanceRepository extends JpaRepository<Attendance, Long> {
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    Optional<Attendance> findWithLockById(Long id);

    Optional<Attendance> findByUserIdAndDate(Long userId, LocalDate date);

    Optional<Attendance> findByUserUsernameAndDate(String username, LocalDate date);

    List<Attendance> findByUserIdOrderByDateDesc(Long userId);

    List<Attendance> findByUserUsernameOrderByDateDesc(String username);

    List<Attendance> findByDate(LocalDate date);

    List<Attendance> findByDateAndStatus(LocalDate date, AttendanceStatus status);

    long countByDateAndStatus(LocalDate date, AttendanceStatus status);

    // NEW: manager/team filtering
    List<Attendance> findByUserInAndDate(Collection<User> users, LocalDate date);

    long countByUserInAndDateAndStatus(Collection<User> users, LocalDate date, AttendanceStatus status);
}

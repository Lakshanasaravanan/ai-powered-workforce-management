package com.slams.repository;

import com.slams.model.LeaveRequest;
import com.slams.model.LeaveStatus;
import com.slams.model.User;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Collection;
import java.util.List;

@Repository
public interface LeaveRequestRepository extends JpaRepository<LeaveRequest, Long> {

    List<LeaveRequest> findByUserIdOrderByAppliedAtDesc(Long userId);

    List<LeaveRequest> findByUserUsernameOrderByAppliedAtDesc(String username);

    List<LeaveRequest> findByStatusOrderByAppliedAtDesc(LeaveStatus status);

    List<LeaveRequest> findByStatus(LeaveStatus status);

    long countByStatus(LeaveStatus status);

    // NEW: for manager/team filtering
    List<LeaveRequest> findByUserInOrderByAppliedAtDesc(Collection<User> users);

    List<LeaveRequest> findByUserInAndStatusOrderByAppliedAtDesc(Collection<User> users, LeaveStatus status);

    long countByUserInAndStatus(Collection<User> users, LeaveStatus status);

    boolean existsByUserIdAndStatusInAndStartDateLessThanEqualAndEndDateGreaterThanEqual(
            Long userId, Collection<LeaveStatus> statuses, java.time.LocalDate endDate, java.time.LocalDate startDate);
}

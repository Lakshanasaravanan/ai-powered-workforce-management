package com.slams.repository;

import com.slams.model.LeaveBalance;
import com.slams.model.User;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
public interface LeaveBalanceRepository extends JpaRepository<LeaveBalance, Long> {

    Optional<LeaveBalance> findByUser(User user);

    Optional<LeaveBalance> findByUserId(Long userId);

    Optional<LeaveBalance> findByUserUsername(String username);
}
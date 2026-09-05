package com.slams.repository;

import com.slams.model.ApprovalStatus;
import com.slams.model.WorkModeRequest;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface WorkModeRequestRepository extends JpaRepository<WorkModeRequest, Long> {

    List<WorkModeRequest> findByEmployeeUsernameOrderByRequestedAtDesc(String username);

    List<WorkModeRequest> findByStatusOrderByRequestedAtDesc(ApprovalStatus status);

    List<WorkModeRequest> findByEmployeeReportingManagerUsernameAndStatusOrderByRequestedAtDesc(
            String managerUsername,
            ApprovalStatus status
    );
}
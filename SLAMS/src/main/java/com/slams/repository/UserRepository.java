package com.slams.repository;

import com.slams.model.Role;
import com.slams.model.User;
import com.slams.model.UserStatus;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Collection;
import java.util.List;
import java.util.Optional;

@Repository
public interface UserRepository extends JpaRepository<User, Long> {

    Optional<User> findByUsername(String username);

    Optional<User> findByEmail(String email);

    boolean existsByUsername(String username);

    boolean existsByEmail(String email);

    boolean existsByEmployeeId(String employeeId);

    List<User> findByRole(Role role);

    List<User> findByRoleIn(Collection<Role> roles);

    List<User> findByReportingManager(User reportingManager);

    List<User> findByReportingManagerAndRole(User reportingManager, Role role);

    List<User> findByReportingManagerAndRoleIn(User reportingManager, Collection<Role> roles);

    List<User> findByStatus(UserStatus status);

    List<User> findByStatusIn(Collection<UserStatus> statuses);

    List<User> findByRoleAndStatus(Role role, UserStatus status);

    List<User> findByDepartmentId(Long departmentId);
}